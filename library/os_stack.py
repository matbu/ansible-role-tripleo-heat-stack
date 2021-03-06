#!/usr/bin/python
#coding: utf-8 -*-

try:
    import time
    from keystoneclient.v2_0 import client as ksclient
    from heatclient.client import Client as hclient
    from heatclient.common import template_utils
    from heatclient.common import utils
    from heatclient import exc
except ImportError:
    print("failed=True msg='heatclient and keystoneclient is required'")

DOCUMENTATION = '''
---
module: os_stack
   - Create, update, list, show, delete and debug failure on heat stack deployment
options:
   login_username:
     description:
        - login username to authenticate to keystone
     required: true
     default: admin
   login_password:
     description:
        - Password of login user
     required: true
     default: True
   login_tenant_name:
     description:
        - The tenant name of the login user
     required: true
     default: True
   auth_url:
     description:
        - The keystone URL for authentication
     required: false
     default: 'http://127.0.0.1:35357/v2.0/'
   region_name:
     description:
        - Name of the region
     required: false
     default: None
   state:
     description:
        - Indicate desired state of the resource
     choices: ['create', 'update', 'list', 'show', 'delete', 'debug']
     default: present
   stack_name:
     description:
        - Name of the stack that should be created
     required: true
     default: None
   template:
     description:
       - Path of the template file to use for the stack creation
     required: false
     default: None
   environment_files:
     description:
        - List of environment files that should be used for the stack creation
     required: false
     default: None
requirements: ["heatclient", "keystoneclient"]
'''

EXAMPLES = '''
# Create a stack with given template and environment files
    - name: create stack
      heat_stack:
        login_username: admin
        login_password: admin
        auth_url: "http://192.168.1.14:5000/v2.0"
        tenant_name: admin
        stack_name: test
        state: create
        template: "/home/stack/ovb/templates/quintupleo.yaml"
        environment_files: ['/home/stack/ovb/templates/resource-registry.yaml','/home/stack/ovb/templates/env.yaml']

    - name: delete stack
      heat_stack:
        stack_name: test
        state: delete
        login_username: admin
        login_password: admin
        auth_url: "http://192.168.1.14:5000/v2.0"
        tenant_name: admin
'''

def obj_gen_to_dict(gen):
    """Enumerate through generator of object and return lists of dictonaries.
    """
    obj_list = []
    for obj in gen:
        obj_list.append(obj.to_dict())
    return obj_list


class Stack(object):

    def __init__(self, kwargs):
        self.client = self._get_client(kwargs)

    def _get_client(self, kwargs, endpoint_type='publicURL'):
        """ get heat client """
        kclient = ksclient.Client(**kwargs)
        token = kclient.auth_token
        endpoint = kclient.service_catalog.url_for(service_type='orchestration',
                                                    endpoint_type=endpoint_type)
        kwargs = {
                'token': token,
        }
        return hclient('1', endpoint=endpoint, token=token)

    def create(self, name,
                template_file,
                env_file=None,
                format='json'):
        """ create heat stack with the given template and environment files """
        self.client.format = format
        tpl_files, template = template_utils.get_template_contents(template_file)
        env_files, env = template_utils.process_multiple_environments_and_files(env_paths=env_file)

        try:
            stack = self.client.stacks.create(stack_name=name,
                                       template=template,
                                       environment=env,
                                       files=dict(list(tpl_files.items()) + list(env_files.items())),
                                       parameters={})
            uid = stack['stack']['id']

            stack = self.client.stacks.get(stack_id=uid).to_dict()
            while stack['stack_status'] == 'CREATE_IN_PROGRESS':
                stack = self.client.stacks.get(stack_id=uid).to_dict()
                time.sleep(5)
            if stack['stack_status'] == 'CREATE_COMPLETE':
                return stack
            else:
                return (False)
        except exc.HTTPBadRequest as e:
            return (False, e)

    def list(self):
        """ list created stacks """
        fields = ['id', 'stack_name', 'stack_status', 'creation_time',
                  'updated_time']
        uids = []
        stacks = self.client.stacks.list()
        utils.print_list(stacks, fields)
        return obj_gen_to_dict(stacks)

    def delete(self, name):
        """ delete stack with the given name """
        self.client.stacks.delete(name)
        return self.list()

    def get(self, name):
        """ show stack """
        return self.client.stacks.get(name)

    def get_id(self, name):
        """ get stack id by name """
        stacks = self.client.stacks.list()
        while True:
            try:
                stack = stacks.next()
                if name == stack.stack_name:
                    return stack.id
            except StopIteration:
                break
                return False

class Resource(object):

    def __init__(self, kwargs):
        self.client = self._get_client(kwargs)

    def _get_client(self, kwargs, endpoint_type='publicURL'):
        """ get heat client """
        kclient = ksclient.Client(**kwargs)
        token = kclient.auth_token
        endpoint = kclient.service_catalog.url_for(service_type='orchestration',
                                                    endpoint_type=endpoint_type)
        kwargs = {
                'token': token,
        }
        return hclient('1', endpoint=endpoint, token=token)

    def list(self, name):
        return [ res for res in self.client.resources.list(stack_id=name) ]

    def get(self, name, status='CREATE_COMPLETE', nested_depth=0):
        return [ res for res in self.client.resources.list(stack_id=name, nested_depth=nested_depth) if status in res.resource_status ]

    def get_software_deployment_by_id(self, id):
        try:
            deployment = self.client.software_deployments.get(id)
            return [(deployment.server_id, deployment.output_values['deploy_stderr'], deployment.status_reason)]
        except exc.HTTPNotFound:
            pass

    def get_software_deployment_by_status(self, status='FAILED'):
        return [ res for res in self.client.software_deployments.list() if status in res.resource_status ]

    def debug_deployment(self, name):
        # get failed resource
        failed_resource = self.get(name=name, status='FAILED', nested_depth=5)
        # get software_deployment
        failure = []
        for res in failed_resource:
            failure.append(self.get_software_deployment_by_id(res.physical_resource_id))
        return failure

    def debug_stack(self, name):
        # return all failed resources
        failed_resource = self.get(name=name, status='FAILED', nested_depth=5)
        return [ (res.resource_name, res.resource_status_reason, res.resource_type) for res in failed_resource ]


def main():
    argument_spec = openstack_argument_spec()
    argument_spec.update(dict(
            stack_name              = dict(required=True),
            template                = dict(default=None),
            environment_files       = dict(default=None, type='list'),
            state                   = dict(default='create', choices=['create', 'update', 'delete', 'list', 'show', 'debug']),
            tenant_name             = dict(default=None),
            timeout                 = dict(default=180),
    ))
    module = AnsibleModule(argument_spec=argument_spec)
    state = module.params['state']
    stack_name = module.params['stack_name']
    template = module.params['template']
    environment_files = module.params['environment_files']
    kwargs = {
                'username':  module.params['login_username'],
                'password':  module.params['login_password'],
                'tenant_name':  module.params['tenant_name'],
                'auth_url':  module.params['auth_url']
            }

    stack = Stack(kwargs)

    if module.params['state'] == 'create':
        stack_id = stack.get_id(stack_name)
        if not stack_id:
            stack = stack.create(name=stack_name,
                                        template_file=template,
                                        env_file=environment_files)
            if not stack[0]:
                module.fail_json(msg="Failed to create stack", result = "failed")
            module.exit_json(changed = True, result = "created" , stack = stack)
        else:
            module.exit_json(changed = False, result = "success" , id = stack_id)
    elif module.params['state'] == 'update':
            module.exit_json(changed = False, result = "Not implemented yet")
    elif module.params['state'] == 'delete':
        stack_id = stack.get_id(stack_name)
        if not stack_id:
            module.exit_json(changed = False, result = "success")
        else:
            stack.delete(stack_name)
            module.exit_json(changed = True, result = "deleted")
    elif module.params['state'] == 'list':
        stack_list = stack.list()
        module.exit_json(changed = True, result = "list" , stack_list = stack_list)
    elif module.params['state'] == 'show':
        stack_show = stack.get(stack_name)
        module.exit_json(changed = True, result = "show" , stack_show = stack_show)
    elif module.params['state'] == 'debug':
        resource = Resource(kwargs)
        failed_resource = resource.debug_stack(stack_name)
        failed_deployment = resource.debug_deployment(stack_name)
        module.exit_json(changed = True, result = "debug" , failed_resource = failed_resource, failed_deployment = failed_deployment)

from ansible.module_utils.basic import *
from ansible.module_utils.openstack import *
if __name__ == '__main__':
    main()
