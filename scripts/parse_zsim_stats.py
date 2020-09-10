#! /usr/bin/env python3

import h5py
import sys
from pathlib import Path
import numpy as np
import math

# The fraction of the stats (from the beginning) that should be omitted. This
# should be < 1. If you want only the last dump, set it close to 1, e.g., 0.999
warmup_percent = 0.0

# If False, all numbers would be printed in their original format
pretty_print = False
# pretty_print = True

# Stats would be printed only for the components that are listed here. This is
# coupled with ZSim's internal naming and its configuration file, where we
# define some names for components (e.g. 'c' for cores); the list must be
# changed to comply with the new names defined in a new configuration file.
# Plus, if a component doesn't exist in the system configuration (e.g., L2),
# obviously it must be removed from the list.  Finally, note that not all stats
# exist in all configurations.  For example, in this script I take that the
# core model is OoO and extract the stats considered for an OoO model; these
# stats do not necessarily exist with other core models.
core_name = 'c'
l1d_name = 'l1d'
l1i_name = 'l1i'
l2_name = 'l2'
llc_name = 'llc'
memctrl_name = 'memctrl'
dram_name = 'DRAM'
components = [core_name, l1d_name, l1i_name, l2_name, llc_name, memctrl_name, dram_name]

system_frequency = 2800 * 1000 * 1000   # Hz 

def show_pretty_raw(number, fp_prec=1):    # This returns 23.1M instead of 23104123
    if not pretty_print: return number

    if number < 1000:
        return '%0.*f' % (fp_prec, number)
    elif number < 1000000:
        return '%0.*fK' % (fp_prec, number/1000)
    elif number < 1000000000:
        return '%0.*fM' % (fp_prec, number/1000/1000)
    else:
        return '%0.*fB' % (fp_prec, number/1000/1000/1000)



def show_pretty_size(number, fp_prec=1):    # This returns 23KB instead of 23104123
    if not pretty_print: return number

    if number < 1024:
        return '%0.*f' % (0, number)
    elif number < 1024*1024:
        return '%0.*fK' % (fp_prec, number/1024)
    elif number < 1024*1024*1024:
        return '%0.*fM' % (fp_prec, number/1024/1024)
    else:
        return '%0.*fB' % (fp_prec, number/1024/1024/1024)



def show_pretty_percent(number, fp_prec=1):
    if not pretty_print: return number

    return '%0.*f' % (fp_prec, 100*number) + '%'



def get_stat_value(stat_pointer, parameter, begin_index=None):
    # stat_pointer: e.g., core stats, l1d stats, etc.
    # parameter: str, e.g., 'cycles', 'instrs', etc.
    # begin_index: int, from which dump onwards we care about the results

    if begin_index == None:
        begin_index = max(0, math.floor(len(stat_pointer[parameter]) * warmup_percent) - 1)
    assert begin_index < len(stat_pointer[parameter]) - 1

    # This is an array of values with len() == core count, where every entry in
    # array corresponds to a particular core
    return np.array(stat_pointer[parameter][-1]) - np.array(stat_pointer[parameter][begin_index])



def divide_stats(a, b):
    if np.sum(b) == 0: return -1
    return np.sum(a) / np.sum(b)



def extract_core_stats(core_stats, core_name):
    cycles = get_stat_value(core_stats, 'cycles')
    contention_cycles = get_stat_value(core_stats, 'cCycles')
    instrs = get_stat_value(core_stats, 'instrs')
    micro_ops = get_stat_value(core_stats, 'uops')
    basic_blocks = get_stat_value(core_stats, 'bbls')
    mispred_branches = get_stat_value(core_stats, 'mispredBranches')

    ipc = divide_stats(instrs, cycles)
    micro_ops_per_clock = divide_stats(micro_ops, cycles)
    branch_ratio = divide_stats(basic_blocks, instrs)
    branch_misspred = divide_stats(mispred_branches, basic_blocks)
    exec_time_seconds = np.max(cycles) / system_frequency

    print('\n{}_stats:'.format(core_name))
    print('--{}_ipc:'.format(core_name), show_pretty_raw(ipc, fp_prec=2))
    print('--{}_uops_per_clock:'.format(core_name), show_pretty_raw(micro_ops_per_clock, fp_prec=2))
    print('--{}_branch_ratio:'.format(core_name), show_pretty_percent(branch_ratio, fp_prec=2))
    print('--{}_branch_misspred_ratio:'.format(core_name), show_pretty_percent(branch_misspred, fp_prec=2))
    print('--{}_workload_execution_time:'.format(core_name), show_pretty_raw(exec_time_seconds, fp_prec=2))



def extract_cache_stats(cache_stats, cache_name):
    cache_hGETS = get_stat_value(cache_stats, 'hGETS')
    cache_hGETX = get_stat_value(cache_stats, 'hGETX')
    if cache_name[:2] == 'l1':  # Filter cache stats
        cache_hGETS += get_stat_value(cache_stats, 'fhGETS')
        cache_hGETX += get_stat_value(cache_stats, 'fhGETX')

    cache_mGETS = get_stat_value(cache_stats, 'mGETS')
    cache_mGETXIM = get_stat_value(cache_stats, 'mGETXIM') # I->M
    cache_mGETXSM = get_stat_value(cache_stats, 'mGETXSM') # S->M (Upgrade misses)
    cache_INV = get_stat_value(cache_stats, 'INV')  # Invs from upper level
    cache_INVX = get_stat_value(cache_stats, 'INVX')    # Downgrades from upper level
    cache_latGETnl = get_stat_value(cache_stats, 'latGETnet') # GET requests latency on next level

    cache_hits = cache_hGETS + cache_hGETX
    cache_misses = cache_mGETS + cache_mGETXIM + cache_mGETXSM
    cache_accesses = cache_hits + cache_misses
    cache_reads = cache_hGETS + cache_mGETS
    cache_writes = cache_hGETX + cache_mGETXIM + cache_mGETXSM
    assert (cache_reads + cache_writes).any() == cache_accesses.any()

    cache_hit_ratio = divide_stats(cache_hits, cache_accesses)
    cache_miss_ratio = divide_stats(cache_misses, cache_accesses)
    cache_read_hit_ratio = divide_stats(cache_hGETS, cache_reads)
    cache_read_miss_ratio = divide_stats(cache_mGETS, cache_reads)
    cache_write_hit_ratio = divide_stats(cache_hGETX, cache_writes)
    cache_write_miss_ratio = divide_stats(cache_mGETXIM + cache_mGETXSM, cache_writes)
    cache_coherence_miss_ratio = divide_stats(cache_mGETXSM, cache_accesses) # Total ratio, not fraction of misses
    cache_inv_ratio = divide_stats(cache_INV, cache_accesses)
    cache_downgrade_ratio = divide_stats(cache_INVX, cache_accesses)

    print('\n{}_stats:'.format(cache_name))
    print('--{}_total_hit_ratio:'.format(cache_name), show_pretty_percent(cache_hit_ratio, fp_prec=2))
    print('--{}_read_hit_ratio:'.format(cache_name), show_pretty_percent(cache_read_hit_ratio, fp_prec=2))
    print('--{}_write_hit_ratio:'.format(cache_name), show_pretty_percent(cache_write_hit_ratio, fp_prec=2))
    print('--{}_coherence_miss_ratio:'.format(cache_name), show_pretty_percent(cache_coherence_miss_ratio, fp_prec=2))
    print('--{}_invalidation_ratio:'.format(cache_name), show_pretty_percent(cache_inv_ratio, fp_prec=2))
    print('--{}_downgrade_ratio:'.format(cache_name), show_pretty_percent(cache_downgrade_ratio, fp_prec=2))



def extract_memctrl_stats(memctrl_stats, memctrl_name):
    mem_total_pages = get_stat_value(memctrl_stats, 'totalPages', begin_index=0)
    llc_compulsory_misses = get_stat_value(memctrl_stats, 'llcCompulsoryMisses')
    llc_total_misses = get_stat_value(memctrl_stats, 'llcTotalMisses')

    memory_footprint = np.sum(mem_total_pages) * 4 * 1024
    mem_unique_access_ratio = divide_stats(llc_compulsory_misses, llc_total_misses)

    print('\n{}_stats:'.format(memctrl_name))
    print('--{}_Footprint:'.format(memctrl_name), show_pretty_size(memory_footprint, fp_prec=2))
    print('--{}_Unique_Access_Ratio:'.format(memctrl_name), show_pretty_percent(mem_unique_access_ratio, fp_prec=2))



def extract_dram_stats(dram_stats, dram_name):
    dram_read_reqs = get_stat_value(dram_stats, 'rd')
    dram_write_reqs = get_stat_value(dram_stats, 'wr')
    dram_total_read_bytes = get_stat_value(dram_stats, 'tot_rd')
    dram_total_write_bytes = get_stat_value(dram_stats, 'tot_wr')
    dram_total_read_latency = get_stat_value(dram_stats, 'rdlat')
    dram_total_write_latency = get_stat_value(dram_stats, 'wrlat')
    dram_read_row_buffer_hits = get_stat_value(dram_stats, 'rdhits')
    dram_write_row_buffer_hits = get_stat_value(dram_stats, 'wrhits')

    dram_total_reqs = dram_read_reqs + dram_write_reqs
    dram_total_transferred_bytes = dram_total_read_bytes + dram_total_write_bytes
    dram_total_latency = dram_total_read_latency + dram_total_write_latency
    dram_total_row_buffer_hits = dram_read_row_buffer_hits + dram_write_row_buffer_hits
    assert dram_total_transferred_bytes.any() == (dram_total_reqs * 64).any(), 'The cache block size is 64B?'

    dram_read_ratio = divide_stats(dram_read_reqs, dram_total_reqs)
    dram_write_ratio = divide_stats(dram_write_reqs, dram_total_reqs)
    dram_traffic_bytes = np.sum(dram_total_transferred_bytes)
    dram_avg_req_latency = divide_stats(dram_total_latency, dram_total_reqs)
    dram_avg_read_latency = divide_stats(dram_total_read_latency, dram_read_reqs)
    dram_avg_write_latency = divide_stats(dram_total_write_latency, dram_write_reqs)
    dram_row_buffer_hit_ratio = divide_stats(dram_total_row_buffer_hits, dram_total_reqs)
    dram_row_buffer_read_hit_ratio = divide_stats(dram_read_row_buffer_hits, dram_read_reqs)
    dram_row_buffer_write_hit_ratio = divide_stats(dram_write_row_buffer_hits, dram_write_reqs)

    print('\n{}_stats:'.format(dram_name))
    print('--{}_Read_Ratio:'.format(dram_name), show_pretty_percent(dram_read_ratio, fp_prec=2))
    print('--{}_Total_Traffic_Bytes:'.format(dram_name), show_pretty_raw(dram_traffic_bytes, fp_prec=2))
    print('--{}_Average_Req_Latency:'.format(dram_name), show_pretty_raw(dram_avg_req_latency, fp_prec=2))
    print('--{}_Average_Read_Latency:'.format(dram_name), show_pretty_raw(dram_avg_read_latency, fp_prec=2))
    print('--{}_Average_Write_Latency:'.format(dram_name), show_pretty_raw(dram_avg_write_latency, fp_prec=2))
    print('--{}_Row_Buffer_Hit_Ratio:'.format(dram_name), show_pretty_percent(dram_row_buffer_hit_ratio, fp_prec=2))



if __name__ == '__main__':

    if (len(sys.argv[1:]) != 1):
        print('Wrong arguments!\nUsage: ./script path/to/experiment/folder')
        exit()

    result_files_list = list(Path(sys.argv[1]).glob('**/zsim.h5'))

    for result_file in result_files_list:

        print('\nFile:', result_file)
        stats = h5py.File(result_file, 'r')
        stats = stats['stats']['root']

        # Simulation stats
        # Here, obviously, we do care about the WHOLE simulation, regardless of
        # how many instructions are used for warm-up
        stats_periods = len(stats[core_name])    # Number of dumps in zsim.h5 file during simulation
        whole_simulated_instructions = get_stat_value(stats[core_name], 'instrs', begin_index=0)  # Do include warmup

        print('\nsimulation stats:')
        print('--instructions:', show_pretty_raw(np.sum(whole_simulated_instructions)))
        print('--stats_dumps:', show_pretty_raw(stats_periods, fp_prec=0))
        print('--warmup_percent:', show_pretty_percent(warmup_percent))

        for c in components:
            if c == core_name: extract_core_stats(stats[c], c)
            elif c in [l1i_name, l1d_name, l2_name, llc_name]: extract_cache_stats(stats[c], c)
            elif c == memctrl_name: extract_memctrl_stats(stats[c], c)
            elif c == dram_name: extract_dram_stats(stats[c], c)
            else: assert False, 'Undefined component {}'.format(c)


        # Inter-component stats

        if True:
            # [DRAM Bandwidth Utilization]
            # Notice the parallelism: application's execution time is determined by
            # the MAXIMUM number of clock cycles among all cores. Measuring DRAM
            # bandwidth, we care about "how many bytes are transferred during
            # application's execution time".
            dram_total_read_bytes = get_stat_value(stats[dram_name], 'tot_rd')
            dram_total_write_bytes = get_stat_value(stats[dram_name], 'tot_wr')
            dram_total_transferred_bytes = dram_total_read_bytes + dram_total_write_bytes
            cycles = get_stat_value(stats[core_name], 'cycles')
            exec_time_seconds = np.max(cycles) / system_frequency
            dram_bandwidth_util_ratio = divide_stats(dram_total_transferred_bytes, exec_time_seconds)
            print('\nmisc stats:')
            print('--{}_bandwidth_utilization_ratio:'.format(dram_name), dram_bandwidth_util_ratio)

        print ()
        print ('___________________________\n')

