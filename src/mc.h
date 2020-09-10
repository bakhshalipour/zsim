#ifndef _MC_H_
#define _MC_H_

#include "config.h"
#include "g_std/g_string.h"
#include "memory_hierarchy.h"
#include <string>
#include "stats.h"
#include "g_std/g_unordered_map.h"

enum ReqType
{
	LOAD = 0,
	STORE
};

class DDRMemory;

class MemoryController : public MemObject {
private:
    DDRMemory * BuildDDRMemory(Config& config, uint32_t frequency, uint32_t domain, g_string _name, const std::string& prefix, uint32_t tBL, double timing_scale);

    g_string name;
    lock_t lock;

    // [Kasraa] With the current code, we may have many die-stacked DRAM
    // modules but up to one off-chip DRAM module. If the project is not about
    // heterogeneous memory systems, by default, the off-chip DRAM should not
    // be used; the number of die-stacked DRAM modules would determine the
    // available bandwidth.

    // External DRAM Configuration
    MemObject *	extDram = nullptr;
    g_string extDramType;

    // Die-Stacked DRAM Configuration
    MemObject ** mcDrams = nullptr;
    uint8_t mcDramsPerCtrl;
    g_string mcDramType;
    uint32_t mapGran;

    // Stats, bookkeeping
    g_unordered_map <Address, uint64_t> uniquePages;
    g_unordered_map <Address, uint64_t> uniqueCacheLines;
    Counter totalPages, llcCompMisses, llcTotalMisses;

public:
    MemoryController(g_string& _name, uint32_t frequency, uint32_t domain, Config& config);
    uint64_t access(MemReq& req);
    const char * getName() { return name.c_str(); };
    void initStats(AggregateStat* parentStat);
};

#endif
