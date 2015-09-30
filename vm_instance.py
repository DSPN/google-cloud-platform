# Copyright 2015 Google Inc. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Creates an Instance VM with common defaults."""
import copy

import common
import default

# Properties for this component
BOOTDISKTYPE = default.BOOTDISK
BOOTDISKSIZE = default.BOOTDISKSIZE
CAN_IP_FWD = default.CAN_IP_FWD
DEVIMAGE = 'devImage'
DISK = default.DISK
DISK_RESOURCES = default.DISK_RESOURCES
INSTANCE_NAME = default.INSTANCE_NAME
MACHINETYPE = default.MACHINETYPE
METADATA = default.METADATA
NETWORK = default.NETWORK
NO_SCOPE = default.NO_SCOPE
PROVIDE_BOOT = default.PROVIDE_BOOT
SERVICE_ACCOUNTS = default.SERVICE_ACCOUNTS
SRCIMAGE = default.SRCIMAGE
TAGS = default.TAGS
ZONE = default.ZONE

# Defaults
DEFAULT_DISKTYPE = 'pd-standard'
DEFAULT_IP_FWD = False
DEFAULT_MACHINETYPE = 'n1-standard-1'
DEFAULT_NETWORK = 'default'
DEFAULT_PROVIDE_BOOT = True
DEFAULT_BOOTDISKSIZE = 10
DEFAULT_DATADISKSIZE = 500
DEFAULT_ZONE = 'us-central1-f'
DEFAULT_PERSISTENT = 'PERSISTENT'
DEFAULT_SERVICE_ACCOUNT = [{
    'email': 'default',
    'scopes': [
        'https://www.googleapis.com/auth/cloud.useraccounts.readonly',
        'https://www.googleapis.com/auth/devstorage.read_only',
        'https://www.googleapis.com/auth/logging.write',
    ]
}]

# Set Metadata Value
ATTACHED_DISKS = 'ATTACHED_DISKS'


def GenerateComputeVM(context):
    """Generates one VM instance resource."""
    name = context.env['name']
    prop = context.properties
    if SRCIMAGE not in prop:
        raise common.Error('"%s" is a mandatory property' % SRCIMAGE)
    boot_disk_type = prop.setdefault(BOOTDISKTYPE, DEFAULT_DISKTYPE)
    prop[default.DISKTYPE] = boot_disk_type
    can_ip_fwd = prop.setdefault(CAN_IP_FWD, DEFAULT_IP_FWD)
    disks = prop.setdefault(default.DISKS, list())
    # Temporary alternative while multiple disks on creation is not allowed
    if disks:
        new_disks = prop.setdefault(default.DISK_RESOURCES, list())
        disks, prop[DISK_RESOURCES] = GenerateDisks(context, disks, new_disks)
    machine_type = prop.setdefault(MACHINETYPE, DEFAULT_MACHINETYPE)
    metadata = prop.setdefault(METADATA, dict())
    network = prop.setdefault(NETWORK, DEFAULT_NETWORK)
    named = INSTANCE_NAME in prop
    provide_boot = prop.setdefault(PROVIDE_BOOT, DEFAULT_PROVIDE_BOOT)
    tags = prop.setdefault(TAGS, dict([('items', [])]))
    vm_name = prop[INSTANCE_NAME] if named else common.AutoName(name,
                                                                default.INSTANCE)
    zone = prop.setdefault(ZONE, DEFAULT_ZONE)
    if provide_boot:
        dev_mode = DEVIMAGE in prop and prop[DEVIMAGE]
        src_image = common.MakeC2DImageLink(prop[SRCIMAGE], dev_mode)
        boot_name = common.AutoName(context.env['name'], default.DISK, 'boot')
        disk_size = (prop[BOOTDISKSIZE] if BOOTDISKSIZE in prop else
                     DEFAULT_BOOTDISKSIZE)
        disk_type = common.MakeLocalComputeLink(context, default.DISKTYPE)
        disks = PrependBootDisk(disks, boot_name, disk_type, disk_size, src_image)
    machine_type = common.MakeLocalComputeLink(context, default.MACHINETYPE)
    network = common.MakeGlobalComputeLink(context, default.NETWORK)
    # To be consistent with Dev console and gcloud, service accounts need to be
    #  explicitly disabled
    remove_scopes = prop[NO_SCOPE] if NO_SCOPE in prop else False
    if remove_scopes and SERVICE_ACCOUNTS in prop:
        prop.pop(SERVICE_ACCOUNTS)
    else:  # Make sure there is a default service account
        prop.setdefault(SERVICE_ACCOUNTS, copy.deepcopy(DEFAULT_SERVICE_ACCOUNT))

    # pyformat: disable
    resource = [
        {
            'name': vm_name,
            'type': default.INSTANCE,
            'properties': {
                'zone': zone,
                'machineType': machine_type,
                'canIpForward': can_ip_fwd,
                'disks': disks,
                'networkInterfaces': [{
                    'network': network,
                    'accessConfigs': [{'name': default.EXTERNAL,
                                       'type': default.ONE_NAT}]
                }],
                'tags': tags,
                'metadata': metadata,
            }
        }
    ]
    # pyformat: enable

    # Pass through any additional property to the VM
    if SERVICE_ACCOUNTS in prop:
        resource[0]['properties'].update({SERVICE_ACCOUNTS: prop[SERVICE_ACCOUNTS]})
    return resource


def PrependBootDisk(disk_list, name, disk_type, disk_size, src_image):
    """Appends the boot disk."""
    # Request boot disk creation (mark for autodelete)
    boot_disk = [{
        'autoDelete': True,
        'boot': True,
        'deviceName': name,
        'initializeParams': {
            'diskType': disk_type,
            'diskSizeGb': disk_size,
            'sourceImage': src_image
        },
        'type': DEFAULT_PERSISTENT,
    }]
    return boot_disk + disk_list


def GenerateDisks(context, disk_list, new_disks):
    """Generates as many disks as passed in the disk_list."""
    project = context.env[default.PROJECT]
    prop = context.properties
    zone = prop.setdefault(ZONE, DEFAULT_ZONE)
    sourced_disks = []
    disk_names = []
    for disk in disk_list:
        d_name = (disk[default.DEVICE_NAME] if default.DISK_NAME not in disk else
                  disk[default.DISK_NAME])
        if default.DISK_SOURCE in disk:  # Existing disk, expect disk api link
            source = disk[default.DISK_SOURCE]
        else:  # The disks should be create separately
            if default.DEVICE_NAME not in disk and default.DISK_NAME not in disk:
                raise common.Error('deviceName or diskName is needed for each disk in '
                                   'this module implemention of multiple disks per vm.')
            disk_init = disk.setdefault(default.INITIALIZEP, dict())
            disk_size = disk_init.setdefault(default.DISK_SIZE, DEFAULT_DATADISKSIZE)
            passed_disk_type = disk_init.setdefault(default.TYPE, DEFAULT_DISKTYPE)
            disk_type = common.LocalComputeLink(
                project, zone, 'diskTypes', passed_disk_type)
            new_disks.append({
                'name': d_name,
                'type': default.DISK,
                'properties': {
                    'type': disk_type,
                    'sizeGb': disk_size,
                    'zone': zone
                }
            })  # pyformat: disable
            disk_names.append(d_name)
            source = common.Ref(d_name)
        sourced_disks.append({
            'deviceName': d_name,
            'autoDelete': True,
            'boot': False,
            'source': source,
            'type': DEFAULT_PERSISTENT,
        })

    items = prop[METADATA].setdefault('items', list())
    items.append({'key': ATTACHED_DISKS, 'value': ','.join(disk_names)})
    return sourced_disks, new_disks


def GenerateResourceList(context):
    """Returns list of resources generated by this module."""
    resources = GenerateComputeVM(context)
    resources += common.AddDiskResourcesIfNeeded(context)
    return resources


@common.FormatErrorsDec
def GenerateConfig(context):
    """Generates YAML resource configuration."""
    return common.MakeResource(GenerateResourceList(context))
