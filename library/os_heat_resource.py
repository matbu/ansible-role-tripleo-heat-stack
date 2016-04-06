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
module: os_heat_resource
   - list, show, and debug resource failure on heat stack deployment
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
   state:
     description:
        - Indicate desired state of the resource
     choices: ['list', 'show', 'debug']
     default: present
   stack_name:
     description:
        - Name of the stack that should be created
     required: true
     default: None
requirements: ["heatclient", "keystoneclient"]
'''

EXAMPLES = '''
# Create a stack with given template and environment files
    - debug: msg="handle debug when failure"
      changed_when: stack_create.result == 'failed'
      notify: debug heat stack on failure
'''

def obj_gen_to_dict(gen):
    """Enumerate through generator of object and return lists of dictonaries.
    """
    obj_list = []
    for obj in gen:
        obj_list.append(obj.to_dict())
    return obj_list


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
            state                   = dict(default='create', choices=['list', 'show', 'debug']),
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

    resource = Resource(kwargs)

    if module.params['state'] == 'list':
        module.exit_json(changed = False, result = "Not implemented yet")
    elif module.params['state'] == 'show':
        module.exit_json(changed = False, result = "Not implemented yet")
    elif module.params['state'] == 'debug':
        failed_resource = resource.debug_stack(stack_name)
        failed_deployment = resource.debug_deployment(stack_name)
        module.exit_json(changed = True, result = "debug" , failed_resource = failed_resource, failed_deployment = failed_deployment)

from ansible.module_utils.basic import *
from ansible.module_utils.openstack import *
if __name__ == '__main__':
    main()
