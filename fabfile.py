import os
import time
import sys
from contextlib import contextmanager

from fabric.api import task, sudo, env, run, execute
from digitalocean import Droplet, Manager


DIGITAL_OCEAN_ACCESS_TOKEN = os.getenv('DIGITAL_OCEAN_ACCESS_TOKEN')

env.user = 'root'
env.hosts = []


# helpers

def get_droplet_status(node):
    """ Given a droplet's tag name, return the status of the droplet """
    manager = Manager(token=DIGITAL_OCEAN_ACCESS_TOKEN)
    droplet = manager.get_all_droplets(tag_name=node)
    return droplet[0].status


@contextmanager
def stdout_redirected(new_stdout):
    save_stdout = sys.stdout
    sys.stdout = new_stdout
    try:
        yield None
    finally:
        sys.stdout = save_stdout


# tasks

@task
def ping(output):
    """ Sanity check """
    print(f'pong!')
    print(f'hello {output}!')


@task
def create_droplets():
    """
    Create three new DigitalOcean droplets -
    node-1, node-2, node-3
    """
    manager = Manager(token=DIGITAL_OCEAN_ACCESS_TOKEN)
    # Get ALL SSH keys
    keys = manager.get_all_sshkeys()
    # Get single SSH key
    # all_keys = manager.get_all_sshkeys()
    # keys = []
    # for key in all_keys:
    #     if key.name == '<ADD_YOUR_KEY_NAME_HERE>':
    #         keys.append(key)
    for num in range(3):
        node = f'node-{num + 1}'
        droplet = Droplet(
            token=DIGITAL_OCEAN_ACCESS_TOKEN,
            name=node,
            region='nyc3',
            image='ubuntu-16-04-x64',
            size_slug='4gb',
            tags=[node],
            ssh_keys=keys,
        )
        droplet.create()
        print(f'{node} has been created.')


@task
def wait_for_droplets():
    """ Wait for each droplet to be ready and active """
    for num in range(3):
        node = f'node-{num + 1}'
        while True:
            status = get_droplet_status(node)
            if status == 'active':
                print(f'{node} is ready.')
                break
            else:
                print(f'{node} is not ready.')
                time.sleep(1)


@task
def destroy_droplets():
    """ Destroy the droplets - node-1, node-2, node-3 """
    manager = Manager(token=DIGITAL_OCEAN_ACCESS_TOKEN)
    droplets = manager.get_all_droplets()
    for num in range(3):
        node = f'node-{num + 1}'
        droplets = manager.get_all_droplets(tag_name=node)
        for droplet in droplets:
            droplet.destroy()
        print(f'{node} has been destroyed.')


@task
def get_addresses(type):
    """ Get IP address """
    manager = Manager(token=DIGITAL_OCEAN_ACCESS_TOKEN)
    if type == 'master':
        droplet = manager.get_all_droplets(tag_name='node-1')
        print(droplet[0].ip_address)
        env.hosts.append(droplet[0].ip_address)
    elif type == 'workers':
        for num in range(2, 4):
            node = f'node-{num}'
            droplet = manager.get_all_droplets(tag_name=node)
            print(droplet[0].ip_address)
            env.hosts.append(droplet[0].ip_address)
    elif type == 'all':
        for num in range(3):
            node = f'node-{num + 1}'
            droplet = manager.get_all_droplets(tag_name=node)
            print(droplet[0].ip_address)
            env.hosts.append(droplet[0].ip_address)
    else:
        print('The "type" should be either "master", "workers", or "all".')
    print(f'Host addresses - {env.hosts}')


@task
def install_docker():
    """ Install Docker """
    print(f'Installing Docker on {env.host}')
    sudo('apt-get update && apt-get install -qy docker.io')
    run('docker --version')


@task
def disable_selinux_swap():
    """
    Disable SELinux so kubernetes can communicate with other hosts
    Disable Swap https://github.com/kubernetes/kubernetes/issues/53533
    """
    sudo('sed -i "/ swap / s/^/#/" /etc/fstab')
    sudo('swapoff -a')


@task
def install_kubernetes():
    """ Install Kubernetes """
    print(f'Installing Kubernetes on {env.host}')
    sudo('apt-get update && apt-get install -y apt-transport-https')
    sudo('curl -s https://packages.cloud.google.com/apt/doc/apt-key.gpg | apt-key add -')
    sudo('echo "deb http://apt.kubernetes.io/ kubernetes-xenial main" | \
          tee -a /etc/apt/sources.list.d/kubernetes.list && apt-get update')
    sudo('apt-get update && apt-get install -y kubelet kubeadm kubectl')


@task
def configure_master():
    """
    Init Kubernetes
    Set up the Kubernetes Config
    Deploy flannel network to the cluster
    """
    sudo('kubeadm init')
    sudo('mkdir -p $HOME/.kube')
    sudo('cp -i /etc/kubernetes/admin.conf $HOME/.kube/config')
    sudo('chown $(id -u):$(id -g) $HOME/.kube/config')
    sudo('kubectl apply -f \
          https://raw.githubusercontent.com/coreos/flannel/master/Documentation/kube-flannel.yml')


@task
def get_join_key():
    token = sudo('kubeadm token create --print-join-command')
    with open('join.txt', "w") as f:
        with stdout_redirected(f):
            print(token)


@task
def configure_worker_node():
    """ Join a worker to the cluster """
    with open('join.txt') as f:
        sudo(f'{f.readline()}')


@task
def get_nodes():
    sudo('kubectl get nodes')


# main tasks

@task
def provision_machines():
    execute(install_docker)
    execute(disable_selinux_swap)
    execute(install_kubernetes)


@task
def create_cluster():
    execute(configure_master)
    execute(get_join_key)
