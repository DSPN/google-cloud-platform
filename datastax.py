import yaml
import random
import string

def GetZonesList(context):
    zones = []
    if context.properties['usEast1b']:
        zones.append('us-east1-b')
    if context.properties['usEast1c']:
        zones.append('us-east1-c')
    if context.properties['usEast1d']:
        zones.append('us-east1-d')
    if context.properties['usCentral1a']:
        zones.append('us-central1-a')
    if context.properties['usCentral1b']:
        zones.append('us-central1-b')
    if context.properties['usCentral1c']:
        zones.append('us-central1-c')
    if context.properties['usCentral1f']:
        zones.append('us-central1-f')
    if context.properties['europeWest1b']:
        zones.append('europe-west1-b')
    if context.properties['europeWest1c']:
        zones.append('europe-west1-c')
    if context.properties['europeWest1d']:
        zones.append('europe-west1-d')
    if context.properties['asiaEast1a']:
        zones.append('asia-east1-a')
    if context.properties['asiaEast1b']:
        zones.append('asia-east1-b')
    if context.properties['asiaEast1c']:
        zones.append('asia-east1-c')
    assert len(zones) > 0, 'No zones selected for DataStax Enterprise nodes'
    return zones


def GenerateConfig(context):
    config = {'resources': []}

    # Set zones list based on zone booleans.
    if ('zones' not in context.properties or len(context.properties['zones']) == 0):
        context.properties['zones'] = GetZonesList(context)

    # Set zone property to match ops center zone. Needed for calls to common.MakeGlobalComputeLink.
    context.properties['zone'] = context.properties['opsCenterZone']
    cluster_name = 'clusters-' + context.env['name']

    # Generate a random bucket name
    bucket_suffix = ''.join([random.choice(string.ascii_lowercase + string.digits) for n in xrange(10)])
    sshkey_bucket = context.env['deployment'] + '-ssh-pub-key-bucket-' + bucket_suffix

    # DSE version
    dse_version = context.properties['dseVersion']

    # Set cassandra's user password
    db_pwd = context.properties['cassandraPwd']

    # Set DataStax Academy credentials
    dsa_username = context.properties['dsa_username']
    dsa_password = context.properties['dsa_password']

    # Set default OpsCenter Admin password
    opsc_admin_pwd = context.properties['opsCenterAdminPwd']

    # Set DC size, number of DCs and cluster's size
    dc_size = context.properties['nodesPerZone']
    num_dcs = len(context.properties['zones'])
    cluster_size = dc_size * num_dcs

    seed_nodes_dns_names = context.env['deployment'] + '-' + context.properties['zones'][0] + '-1-vm.c.' + context.env[
        'project'] + '.internal.'
    opscenter_node_name = context.env['deployment'] + '-opscenter-vm'
    opscenter_dns_name = opscenter_node_name + '.c.' + context.env['project'] + '.internal.'

    # Prepare a storage bucket to store our randomly generated SSH key pair for LCM's DSE install
    ssh_pub_key_bucket = {
        'name': sshkey_bucket,
        'type': 'storage.v1.bucket',
        'properties': {
            'name': sshkey_bucket,
        }
    }    
    config['resources'].append(ssh_pub_key_bucket)

    # Script to run inside a DSE node during instance instantiation
    dse_node_script = '''
        #!/usr/bin/env bash

	# If dse already installed, do nothing
        dpkg -s dse &> /dev/null
        retVal=$?
        if [ $retVal -eq 0 ]; then
          exit 0
        fi

        # Prepare for fresh DSE installation
        mkdir /mnt
        mkfs.ext4 -m 0 -F -E lazy_itable_init=0,lazy_journal_init=0,discard /dev/disk/by-id/google-${HOSTNAME}-data-disk
        mount -o discard,defaults /dev/disk/by-id/google-${HOSTNAME}-data-disk /mnt
        echo "/dev/disk/by-id/google-${HOSTNAME}-data-disk /mnt ext4 discard,defaults 0 2" | tee -a /etc/fstab
        mkdir -p /mnt/data1
        mkdir -p /mnt/data1/data
        mkdir -p /mnt/data1/saved_caches
        mkdir -p /mnt/data1/commitlog
        mkdir -p /mnt/data1/dsefs
        chmod -R 777 /mnt/data1

        ##### Install DSE the LCM way
        cd ~ubuntu
        release="master"
        gsutil cp gs://dse-gcp-marketplace/dse-gcp-install-$release.tar.gz .
        tar -xvf dse-gcp-install-$release.tar.gz
        # install extra OS packages
        pushd dse-gcp-install-$release
        ./extra_packages.sh
        ./install_java.sh -o
        popd

        public_ip=`curl --retry 10 icanhazip.com`
        private_ip=`echo $(hostname -I)`
        node_id=$private_ip
        cluster_name=''' + cluster_name + '''
        rack="rack1"
        db_pwd=''' + db_pwd + '''

        zone=$(curl -s -H "Metadata-Flavor: Google" "http://metadata.google.internal/computeMetadata/v1/instance/zone" | grep -o [[:alnum:]-]*$)
        data_center_name=$zone

        # Retrieve internal OPSC IP address
        opscenter_dns_name=''' + opscenter_dns_name + '''
        opsc_ip=`dig +short $opscenter_dns_name`

        # Grab lcm_pem.pub pubilc key from Google Cloud Storage
        cd ~ubuntu/.ssh/
        sshkey_bucket=''' + sshkey_bucket + '''
        gsutil cp gs://$sshkey_bucket/lcm_pem.pub .
        while [ $? -ne 0 ]
        do
            sleep 1s
            gsutil cp gs://$sshkey_bucket/lcm_pem.pub . 
        done
        chown ubuntu:ubuntu lcm_pem.pub
        cat lcm_pem.pub >> authorized_keys

        pushd ~ubuntu/dse-gcp-install-$release
        opsc_admin_pwd=''' + opsc_admin_pwd + '''

        ./addNode.py \
        --opscpw $opsc_admin_pwd \
        --opsc-ip $opsc_ip \
        --clustername $cluster_name \
        --dcname $data_center_name \
        --rack $rack \
        --pubip $private_ip \
        --privip $private_ip \
        --nodeid $node_id \

        popd
        '''

    zonal_clusters = {
        'name': 'clusters-' + context.env['name'],
        'type': 'regional_multi_vm.py',
        'properties': {
            'sourceImage': 'https://www.googleapis.com/compute/v1/projects/datastax-public/global/images/datastax-enterprise-ubuntu-1604-xenial-v20180824',
            'zones': context.properties['zones'],
            'machineType': context.properties['machineType'],
            'network': context.properties['network'],
            'numberOfVMReplicas': context.properties['nodesPerZone'],
            'disks': [
                {
                    'deviceName': 'vm-data-disk',
                    'type': 'PERSISTENT',
                    'boot': 'false',
                    'autoDelete': 'true',
                    'initializeParams': {
                        'diskType': context.properties['dataDiskType'],
                        'diskSizeGb': context.properties['diskSize']
                    }
                }
            ],
            'bootDiskType': 'pd-standard',
            'bootDiskSizeGb': 20,
            'metadata': {
                'items': [
                    {
                        'key': 'startup-script',
                        'value': dse_node_script
                    }
                ]
            }
        }
    }

    opscenter_script = '''
      #!/usr/bin/env bash

      # If opscenter already installed, do nothing
      dpkg -s opscenter &> /dev/null
      retVal=$?
      if [ $retVal -eq 0 ]; then
        exit 0
      fi
 
      # Prepare for fresh OpsCenter installation
      cd ~ubuntu
      release="master"
      gsutil cp gs://dse-gcp-marketplace/dse-gcp-install-$release.tar.gz .
      tar -xvf dse-gcp-install-$release.tar.gz

      # install extra OS packages, Java, and OpsCenter
      pushd dse-gcp-install-$release
      ./extra_packages.sh
      ./install_java.sh -o
      ./installOpsc.sh

      # Update password for default DSE OpsCenter administrator (admin)
      opsc_admin_pwd=''' + opsc_admin_pwd + '''
      ./set_opsc_pw_https.sh $opsc_admin_pwd
      popd

      # Generate lcm_pem private and pubilc keys
      pushd ~ubuntu/.ssh/
      ssh-keygen -t rsa -N '' -f lcm_pem
      chown ubuntu:ubuntu lcm_pem*
      privkey=$(readlink -f ~ubuntu/.ssh/lcm_pem)
      sshkey_bucket=''' + sshkey_bucket + '''
      gsutil cp ./lcm_pem.pub gs://$sshkey_bucket/
      popd

      # Set up cluster in OpsCenter the LCM way
      cd ~ubuntu/dse-gcp-install-$release

      # Generate cluster name
      cluster_name=''' + cluster_name + '''

      # Generate number of DCs 
      num_dcs=''' + str(num_dcs) + '''

      # Generate cluster size
      cluster_size=''' + str(cluster_size) + '''
    
      # DSE version
      dse_version=''' + dse_version + '''
 
      # Generate cassandra user's password
      db_pwd=''' + db_pwd + '''

      # Generate DataStax Academy credentials
      dsa_username=''' + dsa_username + '''
      dsa_password=''' + dsa_password + '''

      # Retrieve OpsCenter's public IP address
      private_ip=`echo $(hostname -I)`
      
      sleep 1m

      ./setupCluster.py --user ubuntu --pause 60 --opscpw $opsc_admin_pwd --trys 40 --opsc-ip $private_ip --clustername $cluster_name --privkey $privkey --datapath /mnt/data1 --repouser $dsa_username --repopw $dsa_password --dbpasswd $db_pwd --dsever $dse_version
      ./triggerInstall.py --opsc-ip $private_ip --opscpw $opsc_admin_pwd --clustername $cluster_name --clustersize $cluster_size 
      ./waitForJobs.py --num 1 --opsc-ip $private_ip --opscpw $opsc_admin_pwd

      # Alter required keyspaces for multi-DC
      ./alterKeyspaces.py --opscpw $opsc_admin_pwd --delay 60 >> ../../repair.log &

      # Remove public key from Google cloud storage bucket
      gsutil rm gs://$sshkey_bucket/lcm_pem.pub
  
      '''

    opscenter_node_name = context.env['deployment'] + '-opscenter-vm'
    opscenter_node = {
        'name': opscenter_node_name,
        'type': 'vm_instance.py',
        'properties': {
            'instanceName': opscenter_node_name,
            'sourceImage': 'https://www.googleapis.com/compute/v1/projects/datastax-public/global/images/datastax-enterprise-ubuntu-1604-xenial-v20180824',
            'zone': context.properties['opsCenterZone'],
            'machineType': context.properties['machineType'],
            'network': context.properties['network'],
            'bootDiskType': 'pd-standard',
            'serviceAccounts': [{
                'email': 'default',
                'scopes': ['https://www.googleapis.com/auth/compute', 'https://www.googleapis.com/auth/devstorage.full_control']
            }],
            'metadata': {
                'items': [
                    {
                        'key': 'startup-script',
                        'value': opscenter_script
                    }
                ]
            }
        }
    }

    config['resources'].append(zonal_clusters)
    config['resources'].append(opscenter_node)

    first_enterprise_node_name = context.env['deployment'] + '-' + context.properties['zones'][0] + '-1-vm'
    outputs = [
        {
            'name': 'project',
            'value': context.env['project']
        },
        {
            'name': 'opsCenterNodeName',
            'value': opscenter_node_name
        },
        {
            'name': 'firstEnterpriseNodeName',
            'value': first_enterprise_node_name
        },
        {
            'name': 'firstEnterpriseNodeSelfLink',
            'value': '$(ref.' + first_enterprise_node_name + '.selfLink)'
        },
        {
            'name': 'zoneList',
            'value': ', '.join(context.properties['zones'])
        },
        {
            'name': 'x-status-type',
            'value': 'console'
        },
        {
            'name': 'x-status-instance',
            'value': opscenter_node_name
        }
    ]
    config['outputs'] = outputs

    return yaml.dump(config)
