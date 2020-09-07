#include "mc.h"
#include "mem_ctrls.h"
#include "dramsim_mem_ctrl.h"
#include "ddr_mem.h"
#include "zsim.h"
#include <core.h>

MemoryController::MemoryController(g_string& name, uint32_t frequency, uint32_t domain, Config& config)
	: _name (name)
{
	extDramType = config.get<const char *>("sys.mem.ext_dram.type", "DDR");
	g_string extDramName = _name + g_string("-ext");
    if (extDramType == "DDR") {
        extDram = BuildDDRMemory(config, frequency, domain, extDramName, "sys.mem.ext_dram.", 4, 1.0 /*timing_scale*/);
    } else {
        assert(false);  // Other types are not handled now
    }

    mcDramType = config.get<const char *>("sys.mem.mc_dram.type", "DDR");
    mcDramsPerCtrl = config.get<uint32_t>("sys.mem.mc_dram.mc_drams_per_ctrl", 0);
    mcDrams = (MemObject **) gm_malloc(sizeof(MemObject *) * mcDramsPerCtrl);
    mapGran = config.get<uint32_t>("sys.mem.mapGranu", 64);
    for (uint32_t i = 0; i < mcDramsPerCtrl; i++) {
        g_string mcDramName = _name + g_string("-mc-") + g_string(to_string(i).c_str());

        // tBL for die-stacked is 1, so for data access, should multiply by 2, for TAD access, should multiply by 3.
        if (mcDramType == "DDR") {
            mcDrams[i] = BuildDDRMemory(config, frequency, domain, mcDramName, "sys.mem.mcdram.", 4, 1.0 /*timing_scale*/);
        } else {
            assert(false);  // Other types are not handled now
        }
    }
    info("[%s] Created 1 external DRAM and %d MCDRAM modules", name.c_str(), mcDramsPerCtrl);
}

uint64_t 
MemoryController::access(MemReq& req)
{
	switch (req.type) {
        case PUTS:
        case PUTX:
            *req.state = I;
            break;
        case GETS:
            *req.state = req.is(MemReq::NOEXCL)? S : E;
            break;
        case GETX:
            *req.state = M;
            break;
        default: panic("!?");
    }

	if (req.type == PUTS)   return req.cycle; // Ignore clean LLC eviction

    Address lineAddr = req.lineAddr;
    Address pageAddr = lineAddr / (4096 / 64);

    // info("[%s] pc=%lx, addr=%lx", _name.c_str(), req.pc, req.lineAddr);

    // [Stats] Stats, Bookkeeping
    llcTotalMisses.inc();

    if (uniqueCacheLines.find(lineAddr) == uniqueCacheLines.end()) {
        uniqueCacheLines.insert(std::make_pair(lineAddr, (uint64_t)1));
        llcCompMisses.inc();
    } else {
        uniqueCacheLines[lineAddr]++;
    }

    if (uniquePages.find(pageAddr) == uniquePages.end()) {
        uniquePages.insert(std::make_pair(pageAddr, (uint64_t)1));
        totalPages.inc();
    } else {
        uniquePages[pageAddr]++;
    }
    // [Stats]


	futex_lock(&_lock);

    // Only one (off-chip) DRAM module
    req.cycle = extDram->access(req, 0, 4);

    // [Kasraa] This is an example of dispatching requests to different
    // DRAM modules. Requests with the LSB of 1 will be served by the
    // off-chip DRAM; other will be distributed on 4 die-stacked DRAM
    // modules.
    /*
    if (lineAddr & 1) {
        req.cycle = extDram->access(req, 0, 4);	// Load from external dram
    } else {
        uint32_t index = (lineAddr / mapGran) % mcDramsPerCtrl;
        Address mcDramAddr = (lineAddr / 64 / mcDramsPerCtrl * 64) | (lineAddr % 64);
        req.lineAddr = mcDramAddr;
        req.cycle = mcDrams[index]->access(req, 0, 4);	//All requests are served from in-packge DRAM
        req.lineAddr = lineAddr;
    }
    */
	
	futex_unlock(&_lock);

	return req.cycle;
}

DDRMemory* 
MemoryController::BuildDDRMemory(Config& config, uint32_t frequency, 
								 uint32_t domain, g_string name, const string& prefix, uint32_t tBL, double timing_scale) 
{
    uint32_t ranksPerChannel = config.get<uint32_t>(prefix + "ranksPerChannel", 4);
    uint32_t banksPerRank = config.get<uint32_t>(prefix + "banksPerRank", 8);  // DDR3 std is 8
    uint32_t pageSize = config.get<uint32_t>(prefix + "pageSize", 8*1024);  // 1Kb cols, x4 devices
    const char* tech = config.get<const char*>(prefix + "tech", "DDR3-1333-CL10");  // see cpp file for other techs
    const char* addrMapping = config.get<const char*>(prefix + "addrMapping", "rank:col:bank");  // address splitter interleaves channels; row always on top

    // If set, writes are deferred and bursted out to reduce WTR overheads
    bool deferWrites = config.get<bool>(prefix + "deferWrites", true);
    bool closedPage = config.get<bool>(prefix + "closedPage", true);

    // Max row hits before we stop prioritizing further row hits to this bank.
    // Balances throughput and fairness; 0 -> FCFS / high (e.g., -1) -> pure FR-FCFS
    uint32_t maxRowHits = config.get<uint32_t>(prefix + "maxRowHits", 4);

    // Request queues
    uint32_t queueDepth = config.get<uint32_t>(prefix + "queueDepth", 16);
    uint32_t controllerLatency = config.get<uint32_t>(prefix + "controllerLatency", 10);  // in system cycles

    auto mem = new DDRMemory(zinfo->lineSize, pageSize, ranksPerChannel, banksPerRank, frequency, tech,
            addrMapping, controllerLatency, queueDepth, maxRowHits, deferWrites, closedPage, domain, name);
    return mem;
}

void 
MemoryController::initStats(AggregateStat* parentStat)
{
	AggregateStat* memStats = new AggregateStat();
	memStats->init(_name.c_str(), "Memory controller stats");

    totalPages.init("totalPages", "Number of 4KB Pages Touched by the Application"); memStats->append(&totalPages);
    llcCompMisses.init("llcCompulsoryMisses", "Compulsory LLC Misses"); memStats->append(&llcCompMisses);
    llcTotalMisses.init("llcTotalMisses", "Total LLC Misses"); memStats->append(&llcTotalMisses);

	extDram->initStats(memStats);
	for (uint32_t i = 0; i < mcDramsPerCtrl; i++) 
		mcDrams[i]->initStats(memStats);

    parentStat->append(memStats);
}
