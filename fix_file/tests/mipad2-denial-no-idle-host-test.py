#!/usr/bin/env python3
"""Native Denial no-idle backend contracts; no desktop/DBus changes."""
import copy
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import threading
import unittest

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'packages/mipad2-test-no-idle/mp2-test-no-idle-denial'
loader=importlib.machinery.SourceFileLoader('denial_no_idle',str(SOURCE))
spec=importlib.util.spec_from_loader(loader.name,loader);backend=importlib.util.module_from_spec(spec);loader.exec_module(backend)


class BackendTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name);self.backup=self.base/'state/denial.saved.json'
        self.document=dict(revision=3,power=dict(idleDpmsEnabled=True,idleLockEnabled=True,
            idleLockTimeoutMinutes=5,idleSuspendEnabled=False,powerButtonAction='dpms'),lockScreen=dict(authentication=True),unrelated=dict(value=123))
        self.applies=0;self.conflict=False

    def call(self,method,params=None):
        if method=='settings.document.get':return dict(revision=self.document['revision'],document=json.dumps(self.document))
        self.assertEqual(method,'settings.document.apply');self.applies+=1
        self.assertEqual(params['expected_revision'],self.document['revision'])
        if self.conflict:raise ValueError('conflict')
        self.document=json.loads(params['document']);self.document['revision']+=1
        return dict(revision=self.document['revision'],document=json.dumps(self.document))

    def action(self,action):return backend.reconcile(action,self.call,self.backup)

    def test_enable_changes_only_dpms(self):
        old=copy.deepcopy(self.document);result=self.action('enable')
        old['revision']+=1;old['power']['idleDpmsEnabled']=False
        self.assertEqual(self.document,old);self.assertTrue(result['unrelated_settings_preserved'])
        self.assertTrue(backend.read_backup(self.backup));self.assertEqual(self.backup.stat().st_mode&0o777,0o600)

    def test_status_rejects_gnome_only_false_pass(self):
        self.assertRaises(ValueError,self.action,'status');self.assertEqual(self.applies,0)

    def test_status_accepts_native_dpms_disabled_without_mutating(self):
        self.document['power']['idleDpmsEnabled']=False
        self.assertTrue(self.action('status')['automatic_dpms_disabled']);self.assertFalse(self.backup.exists());self.assertEqual(self.applies,0)

    def test_repeated_enable_keeps_original_restore_value(self):
        self.action('enable');data=self.backup.read_bytes();self.action('enable')
        self.assertEqual(self.backup.read_bytes(),data);self.assertEqual(self.applies,1)

    def test_disable_restores_only_owned_field_and_keeps_later_user_settings(self):
        self.action('enable');self.document['unrelated']['value']=999
        self.document['power']['idleLockTimeoutMinutes']=11
        self.action('disable');self.assertTrue(self.document['power']['idleDpmsEnabled'])
        self.assertEqual(self.document['unrelated']['value'],999);self.assertEqual(self.document['power']['idleLockTimeoutMinutes'],11);self.assertFalse(self.backup.exists())

    def test_initial_disabled_stays_disabled_after_disable(self):
        self.document['power']['idleDpmsEnabled']=False;self.action('enable');self.action('disable');self.assertFalse(self.document['power']['idleDpmsEnabled']);self.assertEqual(self.applies,0)

    def test_disable_without_restore_record_does_not_enable_dpms(self):
        self.assertFalse(self.action('disable')['changed']);self.assertEqual(self.applies,0)

    def test_conflict_retains_backup_and_does_not_clobber(self):
        old=copy.deepcopy(self.document);self.conflict=True
        self.assertRaises(ValueError,self.action,'enable');self.assertEqual(self.document,old);self.assertTrue(self.backup.exists())

    def test_restore_conflict_retains_backup(self):
        self.action('enable');self.conflict=True
        self.assertRaises(ValueError,self.action,'disable');self.assertTrue(self.backup.exists());self.assertFalse(self.document['power']['idleDpmsEnabled'])

    def test_independent_reenable_not_overwritten_when_original_was_disabled(self):
        self.document['power']['idleDpmsEnabled']=False;self.action('enable')
        self.document['power']['idleDpmsEnabled']=True
        self.assertRaises(ValueError,self.action,'disable');self.assertTrue(self.backup.exists());self.assertTrue(self.document['power']['idleDpmsEnabled'])

    def test_unknown_schema_rejected_before_backup_or_apply(self):
        del self.document['power']['idleDpmsEnabled']
        self.assertRaises(ValueError,self.action,'enable');self.assertFalse(self.backup.exists());self.assertEqual(self.applies,0)

    def test_invalid_bool_not_coerced(self):
        self.document['power']['idleDpmsEnabled']='false'
        self.assertRaises(ValueError,self.action,'enable');self.assertEqual(self.applies,0)

    def test_symlink_backup_refused(self):
        self.backup.parent.mkdir(mode=0o700);target=self.base/'target';target.write_text('keep');self.backup.symlink_to(target)
        self.assertRaises(ValueError,self.action,'enable');self.assertEqual(target.read_text(),'keep');self.assertEqual(self.applies,0)

    def test_world_readable_backup_refused(self):
        self.action('enable');self.backup.chmod(0o644)
        self.assertRaises(ValueError,self.action,'disable');self.assertTrue(self.backup.exists())

    def test_protocol_rejects_error_and_validates_envelope(self):
        for index,reply in enumerate([dict(version=1,id=1,ok=False,error=dict(code='locked')),dict(version=2,id=1,ok=True,result={})]):
            path=self.base/('socket'+str(index));server=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);server.bind(str(path));server.listen(1)
            def serve():
                try:
                    conn,_=server.accept()
                    with conn:conn.recv(4096);conn.sendall((json.dumps(reply)+'\n').encode())
                finally:server.close()
            worker=threading.Thread(target=serve);worker.start()
            try:self.assertRaises(ValueError,backend.request,path,'settings.document.get')
            finally:worker.join(6);self.assertFalse(worker.is_alive())


class ShellIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name);self.bin=self.base/'bin';self.bin.mkdir()
        self.backend=self.bin/'native-backend'
        self.stub('native-backend','echo "$1" >> "$CALLS"; exit "${NATIVE_RESULT:-0}"')
        self.stub('id','echo 0')
        self.stub('runuser','''while [ "$#" -gt 0 ]; do
 case "$1" in
  */native-backend) exec "$@" ;;
  gsettings) exec "$@" ;;
 esac
 shift
done
exit 2''')
        self.stub('systemctl','''if [ "$1" = is-active ]; then echo active; else echo service-change >> "$CALLS"; fi''')
        self.stub('gsettings','''[ "$1" = set ] && exit 0
case "$3" in
 idle-delay) echo 'uint32 0' ;;
 idle-dim) echo false ;;
 sleep-inactive-*-type) echo "'nothing'" ;;
 *) exit 2 ;;
esac''')
        script=(SOURCE.parent/'mp2-test-no-idle').read_text()
        self.helper=self.base/'helper'
        self.helper.write_text(script.replace('/usr/local/libexec/mp2-test-no-idle-denial',str(self.backend)).replace('/var/lib/mipad2-test-no-idle',str(self.base/'state')))
        self.calls=self.base/'calls'
        self.env=dict(os.environ,PATH=str(self.bin)+':'+os.environ['PATH'],CALLS=str(self.calls))

    def stub(self,name,code):
        p=self.bin/name;p.write_text('#!/bin/sh\n'+code+'\n');p.chmod(0o755)

    def run_helper(self,action,result):
        return subprocess.run(['sh',str(self.helper),action],capture_output=True,text=True,env=self.env|dict(NATIVE_RESULT=str(result)),timeout=10)

    def test_native_status_failure_blocks_legacy_false_pass(self):
        q=self.run_helper('status',1);self.assertNotEqual(q.returncode,0);self.assertNotIn('PASS anti-idle',q.stdout)
        q=self.run_helper('status',0);self.assertEqual(q.returncode,0,q.stderr);self.assertIn('PASS anti-idle',q.stdout)

    def test_native_enable_failure_does_not_claim_enabled(self):
        q=self.run_helper('enable',1);self.assertNotEqual(q.returncode,0);self.assertNotIn('test no-idle enabled',q.stdout)
        self.assertNotIn('service-change',self.calls.read_text())

    def test_native_restore_failure_keeps_inhibitor_active(self):
        q=self.run_helper('disable',1);self.assertNotEqual(q.returncode,0);self.assertNotIn('disabled and previous',q.stdout)
        self.assertNotIn('service-change',self.calls.read_text())


if __name__=='__main__':unittest.main()
