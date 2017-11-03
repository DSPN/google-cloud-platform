#/bin/bash

python image_creator.py \
--project datastax-public \
--disk instance-ubuntu-1404-trusty-v20171026 \
--name datastax-enterprise-ubuntu-1404-trusty-v20171026 \
--description 'DataStax Enterprise Ubuntu 14.04 (10/26) Image' \
--destination-project datastax-public \
--license datastax-public/datastax-enterprise
