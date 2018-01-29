#/bin/bash

python image_creator.py \
--project datastax-public \
--disk instance-ubuntu-1404-trusty-v20180110 \
--name datastax-enterprise-ubuntu-1404-trusty-v20180110 \
--description 'DataStax Enterprise Ubuntu 14.04 (2018/01/10) Image' \
--destination-project datastax-public \
--license datastax-public/datastax-enterprise
