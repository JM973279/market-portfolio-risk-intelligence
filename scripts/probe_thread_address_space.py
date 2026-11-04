"""A controlled memory-reservation probe, not financial workload or Render test."""
import json
import mmap
import resource
import threading
from pathlib import Path


def memory():
    result={}
    for line in Path('/proc/self/status').read_text().splitlines():
        if line.startswith(('VmSize:','VmRSS:','Threads:')):
            result[line.split(':')[0]]=int(line.split()[1])
    return result


def start_thread():
    thread=threading.Thread(target=lambda:None)
    try:thread.start();thread.join();return 'started'
    except RuntimeError as error:return str(error)


def main():
    resource.setrlimit(resource.RLIMIT_AS,(512*1024**2,512*1024**2))
    baseline=memory();reserve=512*1024**2-baseline['VmSize']*1024-4*1024**2
    mapping=mmap.mmap(-1,reserve,flags=mmap.MAP_PRIVATE|mmap.MAP_ANONYMOUS,prot=0)
    constrained=memory();failed=start_thread();mapping.close()
    recovered=start_thread()
    print(json.dumps({'scope':'controlled_uncommitted_virtual_reservation', 'baseline':baseline,
                      'reserved':constrained,'remaining_virtual_headroom_mib':4,
                      'thread_result_while_reserved':failed,'thread_result_after_release':recovered,
                      'stack_rlimit_bytes':resource.getrlimit(resource.RLIMIT_STACK)[0],
                      'nproc_rlimit':resource.getrlimit(resource.RLIMIT_NPROC)[0]}))


if __name__=='__main__':main()
