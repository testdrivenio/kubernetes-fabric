#!/bin/bash


echo "Creating droplets..."
fab create_droplets
fab wait_for_droplets
sleep 20

echo "Provision the droplets..."
fab get_addresses:all provision_machines


echo "Configure the master..."
fab get_addresses:master create_cluster


echo "Configure the workers..."
fab get_addresses:workers configure_worker_node
sleep 20

echo "Running a sanity check..."
fab get_addresses:master get_nodes
