import os
import time
import re
import sys
from contextlib import contextmanager
from fabric import task, Connection
from digitalocean import Droplet, Manager


DIGITAL_OCEAN_ACCESS_TOKEN = os.getenv('DIGITAL_OCEAN_ACCESS_TOKEN')
user = 'root'
hosts = []

# tasks

@task
def ping(ctx, output):
    """ Sanity check """
    print(f'pong!')
    print(f'hello {output}!')


@task
def create_droplets(ctx):
    """
    Create three new DigitalOcean droplets -
    node-1, node-2, node-3
    """
    manager = Manager(token=DIGITAL_OCEAN_ACCESS_TOKEN)
    keys = manager.get_all_sshkeys()
    for num in range(3):
        node = f'node-{num + 1}'
        droplet = Droplet(
            token=DIGITAL_OCEAN_ACCESS_TOKEN,
            name=node,
            region='nyc3',
            image='ubuntu-20-04-x64',
            size_slug='4gb',
            tags=[node],
            ssh_keys=keys,
        )
        droplet.create()
        print(f'{node} has been created.')


@task
def wait_for_droplets(ctx):
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


def get_droplet_status(node):
    """ Given a droplet's tag name, return the status of the droplet """
    manager = Manager(token=DIGITAL_OCEAN_ACCESS_TOKEN)
    droplet = manager.get_all_droplets(tag_name=node)
    return droplet[0].status


@task
def destroy_droplets(ctx):
    """ Destroy the droplets - node-1, node-2, node-3 """
    manager = Manager(token=DIGITAL_OCEAN_ACCESS_TOKEN)
    for num in range(3):
        node = f'node-{num + 1}'
        droplets = manager.get_all_droplets(tag_name=node)
        for droplet in droplets:
            droplet.destroy()
        print(f'{node} has been destroyed.')



@task
def get_addresses(ctx, type):
    """ Get IP address """
    manager = Manager(token=DIGITAL_OCEAN_ACCESS_TOKEN)
    if type == 'master':
        droplet = manager.get_all_droplets(tag_name='node-1')
        print(droplet[0].ip_address)
        hosts.append(droplet[0].ip_address)
    elif type == 'workers':
        for num in range(2, 4):
            node = f'node-{num}'
            droplet = manager.get_all_droplets(tag_name=node)
            print(droplet[0].ip_address)
            hosts.append(droplet[0].ip_address)
    elif type == 'all':
        for num in range(3):
            node = f'node-{num + 1}'
            droplet = manager.get_all_droplets(tag_name=node)
            print(droplet[0].ip_address)
            hosts.append(droplet[0].ip_address)
    else:
        print('The "type" should be either "master", "workers", or "all".')
    print(f'Host addresses - {hosts}')


@task
def install_docker(ctx):
    """ Install Docker """
    print(f'Installing Docker on {ctx.host}')
    ctx.sudo('apt-get update && apt-get install -qy docker.io')
    ctx.run('docker --version')
    ctx.sudo('systemctl enable docker.service')


@task
def disable_selinux_swap(ctx):
    """
    Disable SELinux so kubernetes can communicate with other hosts
    Disable Swap https://github.com/kubernetes/kubernetes/issues/53533
    """
    ctx.sudo('sed -i "/ swap / s/^/#/" /etc/fstab')
    ctx.sudo('swapoff -a')


@task
def install_kubernetes(ctx):
    """ Install Kubernetes """
    print(f'Installing Kubernetes on {ctx.host}')
    ctx.sudo('apt-get update && apt-get install -y apt-transport-https')
    ctx.sudo('curl -s https://packages.cloud.google.com/apt/doc/apt-key.gpg | apt-key add -')
    ctx.sudo('echo "deb http://apt.kubernetes.io/ kubernetes-xenial main" | \
          tee -a /etc/apt/sources.list.d/kubernetes.list && apt-get update')
    ctx.sudo('apt-get update && apt-get install -y kubelet kubeadm kubectl')


@task
def provision_machines(ctx):
    for conn in get_connections(hosts):
        install_docker(conn)
        disable_selinux_swap(conn)
        install_kubernetes(conn)


def get_connections(hosts):
    for host in hosts:
        yield Connection(f"{user}@{host}")


@task
def configure_master(ctx):
    """
    Init Kubernetes
    Set up the Kubernetes Config
    Deploy flannel network to the cluster
    """
    ctx.sudo('kubeadm init')
    ctx.sudo('mkdir -p $HOME/.kube')
    ctx.sudo('cp -i /etc/kubernetes/admin.conf $HOME/.kube/config')
    ctx.sudo('chown $(id -u):$(id -g) $HOME/.kube/config')
    ctx.sudo('kubectl apply -f https://raw.githubusercontent.com/coreos/flannel/master/Documentation/kube-flannel.yml')


@task
def get_join_key(ctx):
    sudo_command_res = ctx.sudo('kubeadm token create --print-join-command')
    token = re.findall("^kubeadm.*$", str(sudo_command_res), re.MULTILINE)[0]

    with open('join.txt', "w") as f:
        with stdout_redirected(f):
            print(token)


@contextmanager
def stdout_redirected(new_stdout):
    save_stdout = sys.stdout
    sys.stdout = new_stdout
    try:
        yield None
    finally:
        sys.stdout = save_stdout


@task
def create_cluster(ctx):
    for conn in get_connections(hosts):
        configure_master(conn)
        get_join_key(conn)


@task
def configure_worker_node(ctx):
    """ Join a worker to the cluster """
    with open('join.txt') as f:
        join_command = f.readline()
        for conn in get_connections(hosts):
            conn.sudo(f'{join_command}')


@task
def get_nodes(ctx):
    for conn in get_connections(hosts):
        conn.sudo('kubectl get nodes')

