#!/bin/bash


echo "Creating droplets..."
fab create-droplets
fab wait-for-droplets
sleep 20

echo "Provision the droplets..."
fab get-addresses --type=all provision-machines


echo "Configure the master..."
fab get-addresses --type=master create-cluster


echo "Configure the workers..."
fab get-addresses --type=workers configure-worker-node
sleep 20

echo "Running a sanity check..."
fab get-addresses --type=master get-nodes