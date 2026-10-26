# SPDX-License-Identifier: MIT
"""Strict terminal metadata ABI6 verifier; never infers frames, pixels or cadence."""
import struct

def require(value,message):
    if not value:raise ValueError(message)

def verify(blob,*,expected_pid,expected_enabled,expected_packets):
    require(type(blob) is bytes and len(blob)==1888,'Expected exact 1888-byte ABI6 snapshot')
    require(type(expected_pid) is int and expected_pid>1,'Invalid expected process')
    require(type(expected_enabled) is bool,'Explicit boolean experiment state required')
    require(type(expected_packets) is int and expected_packets>0,'Actual positive MP4 packet count required')
    magic,version,phases,pid,start,loads,active,early,preearly=struct.unpack_from('<8sII6Q',blob)
    require((magic,version,phases)==(b'MP2I9656',6,26),'Wrong magic/version/phase count')
    require(pid==expected_pid and start>0 and loads>=1,'Wrong process or uninitialized metadata')
    require(active==0,'Driver still active; snapshot is not terminal')
    require(early==preearly==0,'EARLY candidate is not this independent GPU experiment')
    enabled,prepared,uploaded,fallback=struct.unpack_from('<4Q',blob,1856)
    require(enabled==int(expected_enabled),'Experiment flag differs from requested same-binary cell')
    require(prepared==uploaded+fallback,'Unconsumed GPU preparation or counter mismatch')
    if expected_enabled:
        require(prepared==uploaded==expected_packets and fallback==0,'GPU command-path coverage incomplete or CPU fallback occurred')
    else:require(prepared==uploaded==fallback==0,'GPU command path observed in disabled control')
    summaries=[]
    for i in range(26):
        calls,status,total,maximum,cpu,cpu_max,over33,over50=struct.unpack_from('<8Q',blob,64+64*i)
        require(calls==expected_packets and status==0,'Regular encoder phase packet/status mismatch')
        require(maximum<=total and cpu_max<=cpu and over50<=over33<=calls,'Impossible phase aggregate')
        summaries.append(dict(index=i,calls=calls,wall_total_ns=total,wall_max_ns=maximum,cpu_total_ns=cpu,cpu_max_ns=cpu_max,over33=over33,over50=over50))
    return dict(state='terminal-ABI6-metadata-and-requested-GPU-command-coverage-pass',packets=expected_packets,
                GPU_enabled=expected_enabled,GPU_preparations=prepared,GPU_command_uploads=uploaded,GPU_fallbacks=fallback,
                all26_regular_phase_counts_match_MP4=True,phases=summaries,
                GPU_completion_or_descriptor_contents_proven=False,source_frame_or_MP4_identity_proven=False,
                recording_cadence_or_OEM_parity_proven=False,metadata_only=True)
