#!/usr/bin/env python3
"""Build-only candidate verification. Never installs or labels a hang fixed."""
from pathlib import Path
import argparse,hashlib,json,shutil,subprocess,tempfile

MARKER=b'~Module signature appended~\n'

def signed_parts(data):
    if not data.endswith(MARKER) or len(data)<len(MARKER)+12:
        raise ValueError('Missing module signature trailer')
    trailer=data[-len(MARKER)-12:-len(MARKER)]
    length=int.from_bytes(trailer[8:12],'big')
    if trailer[2]!=2 or trailer[3]!=0 or trailer[4]!=0 or any(trailer[5:8]) or length<=0 or length>len(data)-len(MARKER)-12:
        raise ValueError('Invalid PKCS#7 module signature trailer')
    end=len(data)-len(MARKER)-12
    return data[:end-length],data[end-length:end]

def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        while part:=stream.read(1024*1024):h.update(part)
    return h.hexdigest()

def main():
    factory_dsp_flavors = ('tfaqual1', 'tfaqual2')
    camera_flavors = (*(f'lpat{n}' for n in range(14, 28)), 'tfaqual2')
    thermal_flavors = ('lpat3', 'lpat4', 'lpat5', 'lpat6', 'lpat8', 'lpat9',
                       'lpat10', 'lpat11', 'lpat12', 'lpat13', 'tfaqual1', *camera_flavors)
    adc_flavors = ('adc1', 'adc2', 'pmic1', 'lpat1', 'lpat2', *thermal_flavors)
    parser = argparse.ArgumentParser()
    parser.add_argument('--build', type=Path, required=True)
    parser.add_argument('--modules', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--commit', required=True)
    parser.add_argument('--flavor', choices=('daily3', *adc_flavors), default='daily3')
    args = parser.parse_args()
    build=args.build.resolve();modules=args.modules.resolve();output=args.output.resolve()
    if output.exists():raise RuntimeError('Output already exists')
    release=(build/'include/config/kernel.release').read_text().strip()
    if not release.startswith('7.2.') or not release.endswith('-mipad2-integrated-'+args.flavor):raise RuntimeError('Unexpected release')
    config=(build/'.config').read_text()
    if 'CONFIG_EROFS_FS=m\n' not in config:raise RuntimeError('EROFS was not built as a demand-loaded module')
    for option in ['NFT_NAT', 'NFT_MASQ']:
        if f'CONFIG_{option}=m\n' not in config:raise RuntimeError('Missing Android networking option: '+option)
    objects=sorted((modules/'lib/modules'/release).rglob('*.ko*'))
    objects=[p for p in objects if p.name.endswith(('.ko','.ko.zst','.ko.xz','.ko.gz'))]
    if args.flavor in adc_flavors:
        if 'CONFIG_IIO_CHT_WC_ADC=m\n' not in config:raise RuntimeError('ADC was not built as a module')
        if not any(p.name=='intel-chtwc-adc.ko' or p.name.startswith('intel-chtwc-adc.ko.') for p in objects):raise RuntimeError('Missing ADC module')
    if args.flavor in thermal_flavors:
        if 'CONFIG_INTEL_CHTWC_THERMAL=m\n' not in config:
            raise RuntimeError('Board thermal driver was not built as a module')
        thermal_module = 'intel_pmic_chtwc_thermal.ko'
        if not any(p.name == thermal_module or p.name.startswith(thermal_module + '.') for p in objects):
            raise RuntimeError('Missing board thermal module')
    if args.flavor in camera_flavors:
        for symbol, module in (('VIDEO_OV5693', 'ov5693'),
                               ('VIDEO_T4KA3', 't4ka3'),
                               ('VIDEO_ATOMISP', 'atomisp')):
            if f'CONFIG_{symbol}=m\n' not in config or not any(
                    p.name.split('.ko', 1)[0] == module for p in objects):
                raise RuntimeError('Missing guarded camera module: ' + module)
    if len(objects)<32 or not any(p.name.startswith('erofs.ko') for p in objects):raise RuntimeError('Missing matching modules')
    for name in ['nft_chain_nat.ko', 'nft_masq.ko']:
        if not any(p.name == name or p.name.startswith(name+'.') for p in objects):raise RuntimeError('Missing Android networking module: '+name)
    if args.flavor in factory_dsp_flavors:
        options = {
            'CONFIG_SND_SOC_TFA98XX_XIAOMI=m',
            '# CONFIG_SND_SOC_TFA989X is not set',
            'CONFIG_SND_SOC_INTEL_CHT_BSW_RT5659_MACH=m',
            'CONFIG_MODULE_SIG_ALL=y',
        }
        if not options.issubset(config.splitlines()):
            raise RuntimeError('Expected only the factory TFA backend and signed modules')
        names = {p: p.name.split('.ko', 1)[0] for p in objects}
        factory = [p for p, name in names.items() if name == 'snd-soc-tfa98xx-xiaomi']
        if len(factory) != 1 or {'tfa989x', 'snd-soc-tfa989x'} & set(names.values()):
            raise RuntimeError('Invalid factory TFA module set')
        if 'snd-soc-sst-cht-bsw-rt5659' not in names.values():
            raise RuntimeError('Missing RT5659 machine module')
        aliases = subprocess.check_output(['modinfo', '-F', 'alias', str(factory[0])], text=True)
        params = subprocess.check_output(['modinfo', '-F', 'parm', str(factory[0])], text=True)
        firmware = subprocess.check_output(['modinfo', '-F', 'firmware', str(factory[0])], text=True)
        if ('i2c:tfa9890' not in aliases.splitlines() or
                not any(p.startswith('defer_dsp_start:') for p in params.splitlines()) or
                firmware.splitlines() != ['tfa98xx.cnt']):
            raise RuntimeError('Unexpected factory TFA module metadata')
    cert=build/'certs/signing_key.x509';negative_control=False
    with tempfile.TemporaryDirectory(prefix='mipad2-cms-') as tmp:
        tmp=Path(tmp);pem=tmp/'certificate.pem'
        subprocess.run(['openssl','x509','-inform','DER','-in',str(cert),'-out',str(pem)],check=True)
        for path in objects:
            value=subprocess.check_output(['modinfo','-F','vermagic',str(path)],text=True).split()[0]
            if value!=release:raise RuntimeError('Module vermagic mismatch')
            if path.suffix=='.zst':data=subprocess.check_output(['zstd','-q','-d','-c',str(path)])
            elif path.suffix=='.xz':
                import lzma;data=lzma.decompress(path.read_bytes())
            elif path.suffix=='.gz':
                import gzip;data=gzip.decompress(path.read_bytes())
            else:data=path.read_bytes()
            payload,signature=signed_parts(data);(tmp/'payload').write_bytes(payload);(tmp/'signature').write_bytes(signature)
            # -nointern forces the pinned public build certificate. -noverify skips
            # CA-chain policy, not cryptographic content/signature verification.
            command=['openssl','cms','-verify','-binary','-inform','DER','-in',str(tmp/'signature'),'-content',str(tmp/'payload'),'-certfile',str(pem),'-nointern','-noverify','-out','/dev/null']
            q=subprocess.run(command,capture_output=True)
            if q.returncode:raise RuntimeError('CMS verification failed: '+path.name)
            if not negative_control:
                if not payload:raise RuntimeError('Empty module payload')
                (tmp/'payload').write_bytes(bytes([payload[0]^1])+payload[1:])
                if subprocess.run(command,capture_output=True).returncode==0:raise RuntimeError('Corrupted module unexpectedly verified')
                negative_control=True
    output.mkdir(parents=True)
    base=output/'var/lib/mipad2-kernel'/release;base.mkdir(parents=True)
    for source,name in [(build/'arch/x86/boot/bzImage','vmlinuz'),(build/'.config','config'),(build/'System.map','System.map'),(build/'Module.symvers','Module.symvers'),(cert,'module-signing-public.x509')]:shutil.copyfile(source,base/name)
    destination=output/'usr/lib/modules'/release;destination.parent.mkdir(parents=True)
    shutil.copytree(modules/'lib/modules'/release,destination,symlinks=True)
    for name in ['build','source']:
        path=destination/name
        if path.is_symlink():path.unlink()
        elif path.exists():raise RuntimeError('Unexpected source/build object')
    files={str(p.relative_to(output)):sha(p) for p in output.rglob('*') if p.is_file()}
    if any(p.is_symlink() for p in output.rglob('*')):raise RuntimeError('Unexpected retained symlink')
    manifest=dict(kernelrelease=release,source_commit=args.commit,files_sha256=files,module_count=len(objects),all_module_signatures_cryptographically_verified=True,signature_negative_control_passed=negative_control,module_certificate_sha256=sha(cert),installed=False,booted=False,hang_fixed=False,mipad2_navigation_remapping_removed=True,validation='Full build and matching signed-module verification only; hardware/daily/Android validation pending')
    (base/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps({k:v for k,v in manifest.items() if k!='files_sha256'},indent=2))

if __name__=='__main__':main()
