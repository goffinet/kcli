#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
interact with a local/remote libvirt daemon
"""

# from defaults import TEMPLATES
# from distutils.spawn import find_executable
# from netaddr import IPNetwork
import os
import time
from virtualbox import VirtualBox, library, Session
from kvirt import common
import string
import yaml


KB = 1024 * 1024
MB = 1024 * KB
guestrhel532 = "RedHat"
guestrhel564 = "RedHat_64"
guestrhel632 = "RedHat"
guestrhel664 = "RedHat_64"
guestrhel764 = "RedHat_64"
guestother = "Other"
guestotherlinux = "Linux"
guestwindowsxp = "WindowsXP"
guestwindows7 = "Windows7"
guestwindows764 = "Windows7_64"
guestwindows2003 = "Windows2003"
guestwindows200364 = "Windows2003_64"
guestwindows2008 = "Windows2008_64"
guestwindows200864 = "Windows2008_64"
status = {'PoweredOff': 'down', 'PoweredOn': 'up', 'FirstOnline': 'up', 'Aborted': 'down', 'Saved': 'down'}


class Kbox:
    def __init__(self):
        try:
            self.conn = VirtualBox()
        except Exception:
            self.conn = None

    def close(self):
        conn = self.conn
        conn.close()
        self.conn = None

    def exists(self, name):
        conn = self.conn
        for vmname in conn.machines:
            if str(vmname) == name:
                return True
        return False

    def net_exists(self, name):
        conn = self.conn
        networks = []
        for network in conn.internal_networks:
            networks.append(network)
        for network in conn.nat_networks:
            networks.append(network.network_name)
        if name in networks:
            return True
        else:
            return False

    def disk_exists(self, pool, name):
        disks = self.list_disks()
        if name in disks:
            return True
        else:
            return True

    def create(self, name, virttype='vbox', title='', description='kvirt', numcpus=2, memory=512, guestid='Linux_64', pool='default', template=None, disks=[{'size': 10}], disksize=10, diskthin=True, diskinterface='virtio', nets=['default'], iso=None, vnc=False, cloudinit=True, reserveip=False, reservedns=False, start=True, keys=None, cmds=None, ips=None, netmasks=None, gateway=None, nested=True, dns=None, domain=None, tunnel=False, files=[]):
        guestid = 'Linux_64'
        default_diskinterface = diskinterface
        default_diskthin = diskthin
        default_disksize = disksize
        default_pool = pool
        default_poolpath = '/tmp'
        conn = self.conn
        vm = conn.create_machine("", name, [], guestid, "")
        vm.cpu_count = numcpus
        vm.add_storage_controller('SATA', library.StorageBus(2))
        vm.add_storage_controller('IDE', library.StorageBus(1))
        vm.memory_size = memory
        vm.description = description
        vm.set_extra_data('profile', title)
        serial = vm.get_serial_port(0)
        serial.server = True
        serial.enabled = True
        serial.path = str(common.get_free_port())
        serial.host_mode = library.PortMode.tcp
        for index, net in enumerate(nets):
            nic = vm.get_network_adapter(index)
            nic.enabled = True
            nic.attachment_type = library.NetworkAttachmentType.nat
            if index == 0:
                natengine = nic.nat_engine
                natengine.add_redirect('ssh', library.NATProtocol.tcp, '', common.get_free_port(), '', 22)
            if isinstance(net, str):
                # nic.attachment_type = library.NetworkAttachmentType.internal
                # nic.attachment_type = library.NetworkAttachmentType.nat
                # nic.attachment_type = library.NetworkAttachmentType.nat_network
                # nic.internal_network = net
                # nic.nat_network = net
                continue
            elif isinstance(net, dict) and 'name' in net:
                # nic.internal_network = net['name']
                # nic.nat_network = net['name']
                ip = None
                if ips and len(ips) > index and ips[index] is not None:
                    ip = ips[index]
                    nets[index]['ip'] = ip
                elif 'ip' in nets[index]:
                    ip = nets[index]['ip']
                if 'mac' in nets[index]:
                    nic.mac_address = nets[index]['mac'].replace(':', '')
        vm.save_settings()
        conn.register_machine(vm)
        session = Session()
        vm.lock_machine(session, library.LockType.write)
        machine = session.machine
        if cloudinit:
            common.cloudinit(name=name, keys=keys, cmds=cmds, nets=nets, gateway=gateway, dns=dns, domain=domain, reserveip=reserveip, files=files)
            medium = conn.create_medium('RAW', '/tmp/%s.iso' % name, library.AccessMode.read_only, library.DeviceType.dvd)
            progress = medium.create_base_storage(368, [library.MediumVariant.fixed])
            progress.wait_for_completion()
            dvd = conn.open_medium('/tmp/%s.iso' % name, library.DeviceType.dvd, library.AccessMode.read_only, False)
            machine.attach_device("IDE", 0, 0, library.DeviceType.dvd, dvd)
        for index, disk in enumerate(disks):
            if disk is None:
                disksize = default_disksize
                diskthin = default_diskthin
                diskinterface = default_diskinterface
                diskpool = default_pool
                # diskpoolpath = default_poolpath
            elif isinstance(disk, int):
                disksize = disk
                diskthin = default_diskthin
                diskinterface = default_diskinterface
                diskpool = default_pool
                # diskpoolpath = default_poolpath
            elif isinstance(disk, dict):
                disksize = disk.get('size', default_disksize)
                diskthin = disk.get('thin', default_diskthin)
                diskinterface = disk.get('interface', default_diskinterface)
                diskpool = disk.get('pool', default_pool)
                # diskpoolpath = default_poolpath
            else:
                return {'result': 'failure', 'reason': "Invalid disk entry"}
            diskname = "%s_%d" % (name, index)
            if template is not None and index == 0:
                diskpath = self.create_disk(diskname, disksize, pool=diskpool, thin=diskthin, template=template)
                machine.set_extra_data('template', template)
                # return {'result': 'failure', 'reason': "Invalid template %s" % template}
            else:
                diskpath = self.create_disk(diskname, disksize, pool=diskpool, thin=diskthin, template=None)
            disk = conn.open_medium(diskpath, library.DeviceType.hard_disk, library.AccessMode.read_write, False)
            print disksize
            disksize = disksize * 1024 * 1024 * 1024
            progress = disk.resize(disksize)
            progress.wait_for_completion()
            machine.attach_device("SATA", index, 0, library.DeviceType.hard_disk, disk)
        machine.save_settings()
        session.unlock_machine()
        if start:
            self.start(name)
        return {'result': 'success'}
        if iso is None:
            if cloudinit:
                iso = "%s/%s.iso" % (default_poolpath, name)
            else:
                iso = ''
        else:
            try:
                if os.path.isabs(iso):
                    shortiso = os.path.basename(iso)
                else:
                    shortiso = iso
                # iso = "%s/%s" % (default_poolpath, iso)
                # iso = "%s/%s" % (isopath, iso)
                print shortiso
            except:
                return {'result': 'failure', 'reason': "Invalid iso %s" % iso}
        # if nested and virttype == 'kvm':
        #    print "prout"
        # else:
        #    print "prout"
        # if reserveip:
        #    vmxml = ''
        #    macs = []
        #    for element in vmxml.getiterator('interface'):
        #        mac = element.find('mac').get('address')
        #        macs.append(mac)
        #    self._reserve_ip(name, nets, macs)
        # if reservedns:
        #    self._reserve_dns(name, nets, domain)
        return {'result': 'success'}

    def start(self, name):
        conn = self.conn
        try:
            vm = conn.find_machine(name)
            if status[str(vm.state)] == "up":
                return {'result': 'success'}
            else:
                vm = conn.find_machine(name)
                vm.launch_vm_process(None, 'headless', '')

                return {'result': 'success'}
        except:
            return {'result': 'failure', 'reason': "VM %s not found" % name}

    def stop(self, name):
        conn = self.conn
        try:
            vm = conn.find_machine(name)
            if status[str(vm.state)] == "down":
                return {'result': 'success'}
            else:
                session = vm.create_session()
                console = session.console
                console.power_down()
                return {'result': 'success'}
        except:
            return {'result': 'failure', 'reason': "VM %s not found" % name}

    def restart(self, name):
        conn = self.conn
        vm = conn.find_machine(name)
        if status[str(vm.state)] == "down":
            return {'result': 'success'}
        else:
            self.stop(name)
            time.sleep(5)
            self.start(name)
            return {'result': 'success'}

    def report(self):
        conn = self.conn
        host = conn.host
        hostname = os.uname()[1]
        cpus = host.processor_count
        memory = host.memory_size
        print("Host:%s Cpu:%s Memory:%sMB\n" % (hostname, cpus, memory))
        for pool in self._pool_info():
            poolname = pool['name']
            pooltype = 'dir'
            poolpath = pool['path']
            # used = "%.2f" % (float(s[2]) / 1024 / 1024 / 1024)
            # available = "%.2f" % (float(s[3]) / 1024 / 1024 / 1024)
            # Type,Status, Total space in Gb, Available space in Gb
            # print("Storage:%s Type:%s Path:%s Used space:%sGB Available space:%sGB" % (poolname, pooltype, poolpath, used, available))
            print("Storage:%s Type:%s Path:%s" % (poolname, pooltype, poolpath))
        print
        dhcp = {}
        dhcpservers = conn.dhcp_servers
        for dhcpserver in dhcpservers:
            dhcp[dhcpserver.network_name] = dhcpserver.ip_address
        for network in conn.internal_networks:
            print("Network:%s Type:internal" % (network))
        for network in conn.nat_networks:
            print("Network:%s Type:routed" % (network))
        return
        # print("Network:%s Type:routed Cidr:%s Dhcp:%s" % (networkname, cidr, dhcp))

    def status(self, name):
        conn = self.conn
        try:
            vm = conn.find_machine(name)
        except:
            return None
        return status[str(str(vm.state))]

    def list(self):
        vms = []
        # leases = {}
        conn = self.conn
        for vm in conn.machines:
            name = vm.name
            state = status[str(vm.state)]
            port = ''
            source = vm.get_extra_data('template')
            description = vm.description
            profile = vm.get_extra_data('profile')
            for n in range(7):
                nic = vm.get_network_adapter(n)
                enabled = nic.enabled
                if not enabled:
                    continue
                # elif str(nic.attachment_type) == 'NATNetwork':
                #    networktype = 'natnetwork'
                #    network = nic.nat_network
                if str(nic.attachment_type) == 'NAT':
                    for redirect in nic.nat_engine.redirects:
                        redirect = redirect.split(',')
                        hostport = redirect[3]
                        guestport = redirect[5]
                        if guestport == '22':
                            port = hostport
                            break
            vms.append([name, state, port, source, description, profile])
        return vms

    def console(self, name, tunnel=False):
        conn = self.conn
        try:
            vm = conn.find_machine(name)
        except:
            print "VM %s not found" % name
            return
        if self.status(name) == 'down':
            vm.launch_vm_process(None, 'gui', '')
        else:
            print "VM %s allready running in headless mode" % name

    def serialconsole(self, name):
        conn = self.conn
        vm = conn.find_machine(name)
        if not str(vm.state):
            print("VM down")
            return
        else:
            serial = vm.get_serial_port(0)
            if not serial.enabled:
                print("No serial Console found. Leaving...")
                return
            serialport = serial.path
            os.system("nc 127.0.0.1 %s" % serialport)

    def info(self, name):
        # ips = []
        # leases = {}
        starts = {False: 'no', True: 'yes'}
        conn = self.conn
        # for network in conn.listAllNetworks():
        #    for lease in network.DHCPLeases():
        #        ip = lease['ipaddr']
        #        mac = lease['mac']
        #        leases[mac] = ip
        try:
            vm = conn.find_machine(name)
        except:
            print("VM %s not found" % name)
            return
        state = 'down'
        hostports = []
        autostart = starts[vm.autostart_enabled]
        memory = vm.memory_size
        numcpus = vm.cpu_count
        state = status[str(vm.state)]
        print("name: %s" % name)
        print("status: %s" % state)
        print("autostart: %s" % autostart)
        description = vm.description
        print("description: %s" % description)
        profile = vm.get_extra_data('profile')
        if profile != '':
            print("profile: %s" % profile)
        print("cpus: %s" % numcpus)
        print("memory: %sMB" % memory)
        for n in range(7):
            nic = vm.get_network_adapter(n)
            enabled = nic.enabled
            if not enabled:
                break
            device = "eth%s" % n
            mac = ':'.join(nic.mac_address[i: i + 2] for i in range(0, len(nic.mac_address), 2))
            if str(nic.attachment_type) == 'Internal':
                networktype = 'internal'
                network = nic.internal_network
            elif str(nic.attachment_type) == 'NATNetwork':
                networktype = 'natnetwork'
                network = nic.nat_network
            elif str(nic.attachment_type) == 'Null':
                networktype = 'unassigned'
                network = 'N/A'
            elif str(nic.attachment_type) == 'Bridged':
                networktype = 'bridged'
                network = nic.bridged_interface
            elif str(nic.attachment_type) == 'NAT':
                networktype = 'nat'
                network = 'N/A'
                for redirect in nic.nat_engine.redirects:
                    redirect = redirect.split(',')
                    hostport = redirect[3]
                    guestport = redirect[5]
                    if guestport == '22':
                        hostports.append(hostport)
            else:
                networktype = 'N/A'
                network = 'N/A'
            print("net interfaces:%s mac: %s net: %s type: %s" % (device, mac, network, networktype))
        disks = []
        for index in range(10):
            try:
                disk = vm.get_medium('SATA', index, 0)
            except:
                continue
            path = disk.name
            if path.endswith('.iso'):
                continue
            device = 'sd%s' % string.lowercase[len(disks)]
            disks.append(0)
            disksize = disk.size / 1024 / 1024 / 1024
            drivertype = os.path.splitext(disk.name)[1].replace('.', '')
            diskformat = 'file'
            print("diskname: %s disksize: %sGB diskformat: %s type: %s path: %s" % (device, disksize, diskformat, drivertype, path))
            for hostport in hostports:
                print("ssh port: %s" % (hostport))
        return

    def ip(self, name):
        conn = self.conn
        try:
            vm = conn.find_machine(name)
        except:
            print("VM %s not found" % name)
            return None
        # session = vm.create_session()
        # guest = session.console.guest
        natnetworks = conn.nat_networks
        print natnetworks
        for n in natnetworks:
            print dir(n)
        properties = vm.get_guest_property('/VirtualBox/GuestInfo/Net/0/V4/IP')
        print properties

    def volumes(self, iso=False):
        isos = []
        templates = []
        poolinfo = self._pool_info()
        for pool in poolinfo:
            path = pool['path']
            for entry in os.listdir(path):
                if entry.endswith('qcow2') and entry not in templates:
                    templates.append(entry)
                elif entry.startswith('KVIRT'):
                    entry = entry.replace('KVIRT_', '').replace('.vdi', '.qcow2')
                    if entry not in templates:
                        templates.append(entry)
                elif entry.endswith('iso'):
                    isos.append(entry)
        if iso:
            return isos
        else:
            return templates

    def delete(self, name):
        conn = self.conn
        try:
            vm = conn.find_machine(name)
        except:
            return
        vm.remove(True)

    def clone(self, old, new, full=False, start=False):
        conn = self.conn
        tree = ''
        uuid = tree.getiterator('uuid')[0]
        tree.remove(uuid)
        for vmname in tree.getiterator('name'):
            vmname.text = new
        firstdisk = True
        for disk in tree.getiterator('disk'):
            if firstdisk or full:
                source = disk.find('source')
                oldpath = source.get('file')
                backingstore = disk.find('backingStore')
                backing = None
                for b in backingstore.getiterator():
                    backingstoresource = b.find('source')
                    if backingstoresource is not None:
                        backing = backingstoresource.get('file')
                newpath = oldpath.replace(old, new)
                source.set('file', newpath)
                oldvolume = conn.storageVolLookupByPath(oldpath)
                oldinfo = oldvolume.info()
                oldvolumesize = (float(oldinfo[1]) / 1024 / 1024 / 1024)
                newvolumexml = self._xmlvolume(newpath, oldvolumesize, backing)
                pool = oldvolume.storagePoolLookupByVolume()
                pool.createXMLFrom(newvolumexml, oldvolume, 0)
                firstdisk = False
            else:
                devices = tree.getiterator('devices')[0]
                devices.remove(disk)
        for interface in tree.getiterator('interface'):
            mac = interface.find('mac')
            interface.remove(mac)
        if self.host not in ['127.0.0.1', 'localhost']:
            for serial in tree.getiterator('serial'):
                source = serial.find('source')
                source.set('service', str(common.get_free_port()))
        vm = conn.lookupByName(new)
        if start:
            vm.setAutostart(1)
            vm.create()

    def update_ip(self, name, ip):
        conn = self.conn
        try:
            vm = conn.find_machine(name)
        except:
            print("VM %s not found" % name)
            return
        session = Session()
        vm.lock_machine(session, library.LockType.write)
        machine = session.machine
        machine.set_extra_data('ip', ip)
        machine.save_settings()
        session.unlock_machine()

    def update_memory(self, name, memory):
        conn = self.conn
        memory = str(int(memory) * 1024)
        try:
            vm = conn.find_machine(name)
        except:
            print("VM %s not found" % name)
            return
        session = Session()
        vm.lock_machine(session, library.LockType.write)
        machine = session.machine
        machine.memory_size = memory
        machine.save_settings()
        session.unlock_machine()

    def update_cpu(self, name, numcpus):
        conn = self.conn
        try:
            vm = conn.find_machine(name)
        except:
            print("VM %s not found" % name)
            return
        vm.cpu_count = numcpus
        vm.save_settings()

    def update_start(self, name, start=True):
        conn = self.conn
        try:
            vm = conn.find_machine(name)
        except:
            print("VM %s not found" % name)
            return {'result': 'failure', 'reason': "VM %s not found" % name}
        if start:
            vm.autostart_enabled = True
        else:
            vm.autostart_enabled = False
        vm.save_settings()
        return {'result': 'success'}

    def _convert_qcow2(self, name, newname=None):
        if newname is None:
            newname = "KVIRT_%s" % name.replace('qcow2', 'vdi')
        os.system("qemu-img convert -f qcow2 %s -O vdi %s" % (name, newname))

    def create_disk(self, name, size, pool=None, thin=True, template=None):
        conn = self.conn
        # diskformat = 'qcow2'
        if size < 1:
            print("Incorrect size.Leaving...")
            return
        size = int(size) * 1024 * 1024 * 1024
        # if not thin:
        #     diskformat = 'raw'
        if pool is not None:
            pool = [p['path'] for p in self._pool_info() if p['name'] == pool]
            if pool:
                poolpath = pool[0]
            else:
                print("Pool not found. Leaving....")
                return
        diskpath = "%s/%s.vdi" % (poolpath, name)
        if template is not None:
            volumes = self.volumes()
            if template not in volumes and template not in volumes.values():
                print("Invalid template %s.Leaving..." % template)
                return
            # if template.endswith('qcow2'):
            #    templatepath = "%s/KVIRT_%s" % (poolpath, template.replace('qcow2', 'vdi'))
            templatepath = "%s/%s" % (poolpath, template)
        disk = conn.create_medium('VDI', diskpath, library.AccessMode.read_write, library.DeviceType.hard_disk)
        if template in volumes:
            self._convert_qcow2(templatepath, diskpath)
            # template = conn.open_medium(templatepath, library.DeviceType.hard_disk, library.AccessMode.read_write, False)
            # progress = template.clone_to(disk, [library.MediumVariant.fixed], disk)
            # progress.wait_for_completion()
        else:
            progress = disk.create_base_storage(size, [library.MediumVariant.fixed])
            progress.wait_for_completion()
        return diskpath

    def add_disk(self, name, size, pool=None, thin=True, template=None, shareable=False, existing=None):
        conn = self.conn
        # diskformat = 'qcow2'
        if size < 1:
            print("Incorrect size.Leaving...")
            return
        # if not thin:
        #     diskformat = 'raw'
        try:
            vm = conn.find_machine(name)
        except:
            print("VM %s not found" % name)
            return
        disks = []
        for index, dev in enumerate(string.lowercase[:10]):
            try:
                vm.get_medium('SATA', index, 0)
                disks.append(0)
            except:
                continue
        index = len(disks)
        if existing is None:
            storagename = "%s_%d" % (name, index)
            diskpath = self.create_disk(name=storagename, size=size, pool=pool, thin=thin, template=template)
        else:
            disks = self.list_disks()
            if existing in disks:
                diskpath = disks[existing]['path']
            else:
                diskpath = existing
        session = Session()
        vm.lock_machine(session, library.LockType.write)
        machine = session.machine
        disk = conn.open_medium(diskpath, library.DeviceType.hard_disk, library.AccessMode.read_write, True)
        machine.attach_device("SATA", index, 0, library.DeviceType.hard_disk, disk)
        machine.save_settings()
        session.unlock_machine()

    def delete_disk(self, name, diskname):
        conn = self.conn
        try:
            vm = conn.find_machine(name)
        except:
            print("VM %s not found" % name)
            return
        if status[str(vm.state)] == "up":
            print("VM %s up. Leaving" % name)
            return
        for index in range(10):
            try:
                disk = vm.get_medium('SATA', index, 0)
            except:
                continue
            if disk.name == diskname:
                session = Session()
                vm.lock_machine(session, library.LockType.write)
                machine = session.machine
                machine.detach_device("SATA", index, 0)
                machine.save_settings()
                session.unlock_machine()
                disk.delete_storage()
                return
        print("Disk %s not found in %s" % (diskname, name))

    def list_disks(self):
        volumes = {}
        poolinfo = self._pool_info()
        for pool in poolinfo:
            poolname = pool['name']
            path = pool['path']
            for entry in os.listdir(path):
                if entry.endswith('vdi'):
                    volumes[entry] = {'pool': poolname, 'path': "%s/%s" % (path, entry)}
                else:
                    continue
        return volumes
        # volumes = {}
        # interface = library.IVirtualBox()
        # poolinfo = self._pool_info()
        # for disk in interface.hard_disks:
        #     path = disk.location
        #     if poolinfo is not None:
        #         pathdir = os.path.dirname(path)
        #         pools = [pool['name'] for pool in poolinfo if pool['path'] == pathdir]
        #         if pools:
        #             pool = pools[0]
        #         else:
        #             pool = ''
        #     else:
        #         pool = ''
        #     volumes[disk.name] = {'pool': pool, 'path': disk.location}
        # return volumes

    def add_nic(self, name, network):
        conn = self.conn
        networks = self.list_networks()
        if network not in networks:
            print("Network %s not found" % network)
            return
        networktype = networks[network]['type']
        try:
            vm = conn.find_machine(name)
        except:
            print("VM %s not found" % name)
            return
        if self.status(name) == 'up':
            print("VM %s must be down" % name)
            return
        session = Session()
        # try:
        #     vm.unlock_machine()
        # except:
        #     pass
        vm.lock_machine(session, library.LockType.write)
        machine = session.machine
        for n in range(7):
            nic = machine.get_network_adapter(n)
            if not nic.enabled:
                nic.enabled = True
                nic.nat_network = network
                if networktype == 'internal':
                    nic.attachment_type = library.NetworkAttachmentType.internal
                    nic.internal_network = network
                else:
                    nic.attachment_type = library.NetworkAttachmentType.nat_network
                    nic.nat_network = network
                break
        machine.save_settings()
        session.unlock_machine()

    def delete_nic(self, name, interface):
        conn = self.conn
        try:
            vm = conn.find_machine(name)
        except:
            print("VM %s not found" % name)
            return
        if self.status(name) == 'up':
            print("VM %s must be down" % name)
            return
        session = Session()
        vm.lock_machine(session, library.LockType.write)
        machine = session.machine
        number = int(interface[-1])
        nic = machine.get_network_adapter(number)
        nic.enabled = False
        machine.save_settings()
        session.unlock_machine()

    def _ssh_credentials(self, name):
        ubuntus = ['utopic', 'vivid', 'wily', 'xenial', 'yakkety']
        user = 'root'
        conn = self.conn
        try:
            vm = conn.find_machine(name)
        except:
            print("VM %s not found" % name)
            return '', ''
        if str(vm.state) == 0:
            print("Machine down. Cannot ssh...")
            return '', ''
        vm = [v for v in self.list() if v[0] == name][0]
        template = vm[3]
        if template != '':
            if 'centos' in template.lower():
                user = 'centos'
            elif 'cirros' in template.lower():
                user = 'cirros'
            elif [x for x in ubuntus if x in template.lower()]:
                user = 'ubuntu'
            elif 'fedora' in template.lower():
                user = 'fedora'
            elif 'rhel' in template.lower():
                user = 'cloud-user'
            elif 'debian' in template.lower():
                user = 'debian'
            elif 'arch' in template.lower():
                user = 'arch'
        port = vm[2]
        if port == '':
            print("No port found. Cannot ssh...")
        return user, port

    def ssh(self, name, local=None, remote=None, tunnel=False):
        user, port = self._ssh_credentials(name)
        if port == '':
            return
        else:
            sshcommand = "-p %s %s@127.0.0.1" % (port, user)
            if local is not None:
                sshcommand = "-L %s %s" % (local, sshcommand)
            if remote is not None:
                sshcommand = "-R %s %s" % (remote, sshcommand)
            sshcommand = "ssh %s" % sshcommand
            os.system(sshcommand)

    def scp(self, name, source=None, destination=None, tunnel=False, download=False, recursive=False):
        user, port = self._ssh_credentials(name)
        if port == '':
            print("No ip found. Cannot scp...")
        else:
            scpcommand = 'scp -P %s' % port
            if recursive:
                scpcommand = "%s -r" % scpcommand
            if download:
                scpcommand = "%s %s@127.0.0.1:%s %s" % (scpcommand, user, source, destination)
            else:
                scpcommand = "%s %s %s@127.0.0.1:%s" % (scpcommand, source, user, destination)
            os.system(scpcommand)

    def create_pool(self, name, poolpath, pooltype='dir', user='qemu'):
        pools = self.list_pools()
        poolpath = os.path.expanduser(poolpath)
        if name in pools:
            return
        if not os.path.exists(poolpath):
            os.makedirs(poolpath)
        poolfile = "%s/.vbox.yml" % os.environ.get('HOME')
        if not os.path.exists(poolfile):
            poolinfo = [{'name': name, 'path': poolpath}]
        else:
            poolinfo = self._pool_info()
            poolinfo.append({'name': name, 'path': poolpath})
        with open(poolfile, 'w') as f:
            for pool in poolinfo:
                f.write("\n- name: %s\n" % pool['name'])
                f.write("  path: %s" % pool['path'])

    def add_image(self, image, pool):
        if pool is not None:
            pool = [p['path'] for p in self._pool_info() if p['name'] == pool]
            if pool:
                poolpath = pool[0]
            else:
                print("Pool not found. Leaving....")
                return
        cmd = 'wget -P %s %s' % (poolpath, image)
        os.system(cmd)
        return {'result': 'success'}

    def create_network(self, name, cidr, dhcp=True, nat=True):
        conn = self.conn
        network = conn.create_nat_network(name)
        network.network = cidr
        if dhcp:
            network.need_dhcp_server = True
        return {'result': 'success'}

    def delete_network(self, name=None):
        conn = self.conn
        for network in conn.nat_networks:
            networkname = network.network_name
            if networkname == name:
                conn.remove_nat_network(network)
                return {'result': 'success'}
        return {'result': 'failure', 'reason': "Network %s not found" % name}
        # machines = self.network_ports(name)
        # if machines:
        #     machines = ','.join(machines)
        #     return {'result': 'failure', 'reason': "Network %s is being used by %s" % (name, machines)}
        # if network.isActive():
        #     network.destroy()
        # network.undefine()
        # return {'result': 'success'}

    def _pool_info(self):
        poolfile = "%s/.vbox.yml" % os.environ.get('HOME')
        if not os.path.exists(poolfile):
            return None
        with open(poolfile, 'r') as entries:
            poolinfo = yaml.load(entries)
        return poolinfo

    def list_pools(self):
        poolinfo = self._pool_info()
        if poolinfo is None:
            return []
        else:
            return [pool['name'] for pool in poolinfo]

    def list_networks(self):
        networks = {}
        conn = self.conn
        for network in conn.internal_networks:
            networkname = network
            cidr = 'N/A'
            networks[networkname] = {'cidr': cidr, 'dhcp': False, 'type': 'internal', 'mode': 'isolated'}
        for network in conn.nat_networks:
            networkname = network.network_name
            if network.need_dhcp_server:
                dhcp = True
            else:
                dhcp = False
            cidr = network.network
            networks[networkname] = {'cidr': cidr, 'dhcp': dhcp, 'type': 'routed', 'mode': 'nat'}
        return networks

    def delete_pool(self, name, full=False):
        poolfile = "%s/.vbox.yml" % os.environ.get('HOME')
        pools = self.list_pools()
        if not os.path.exists(poolfile) or name not in pools:
            return
        else:
            poolinfo = self._pool_info()
            with open(poolfile, 'w') as f:
                for pool in poolinfo:
                    if pool['name'] == name:
                        continue
                    else:
                        f.write("- name: %s\n" % pool['name'])
                        f.write("  path: %s" % pool['path'])

    def bootstrap(self, pool=None, poolpath=None, pooltype='dir', nets={}, image=None):
        print "Not implemented at the moment"
        poolfile = "%s/.vbox.yml" % os.environ.get('HOME')
        if os.path.exists(poolfile):
            return
        poolinfo = [{'name': pool, 'path': poolpath}]
        with open(poolfile, 'w') as f:
            for pool in poolinfo:
                f.write("\n- name: %s\n" % pool['name'])
                f.write("  path: %s" % pool['path'])
