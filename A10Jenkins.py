#!/usr/bin/python

import json
import requests
import sys
import os


class A10Jenkins(object):

    def __init__(self):
        auth_file = '/app/a10_jenkins/conf/secrets.ini'

        try:
            file = open(auth_file, 'r').readlines()
        except IOError:
            print "ERROR: Unable to open %s" % auth_file
            sys.exit(1)

        self.user = file[0].strip()
        self.password = file[1].strip()

        if os.getenv('load_balancer') is not None:
            self.lb_ipaddress = os.getenv('load_balancer')
            self.rest_api = 'http://' + self.lb_ipaddress + ':80/services/rest/V2.1/'
        else:
            print "ERROR: load_balancer parameter not passed"
            sys.exit(2)

        if os.getenv('hostname') is not None:
            self.hostname = os.getenv('hostname')
        else:
            print "ERROR: hostname parameter not passed"
            sys.exit(2)

        if os.getenv('status') is not None:
            self.status = os.getenv('status')
        else:
            print "ERROR: hostname parameter not passed"
            sys.exit(2)

        if os.getenv('service_group') is not None:
            self.service_group = os.getenv('service_group')
        else:
            print "ERROR: service_group parameter not passed"
            sys.exit(2)

        if os.getenv('port') is not None:
            self.port = os.getenv('port')
        else:
            print "ERROR: port parameter not passed"
            sys.exit(2)

        self.service_group_list = []
        self.server_list = []

    def authenticate(self):
        # Connect to the Load balanceer and get a session id.
        auth_params = {'method':'authenticate', 'username':self.user, 'password':self.password, 'format':'json'}
        try:
            response = requests.get(self.rest_api, params = auth_params)
            data = json.loads(response.text)
            self.session_id = data['session_id']
        except KeyError:
            print "ERROR: Unable to get session_id from %s" % self.rest_api
            sys.exit(2)

    def get_a10_data(self):
        # Get all service groups the from Load Balancer. Data will be used to verify parameters 
        # passed are in the Load Balancer.
        service_group_params = {'session_id':self.session_id, 'method':'slb.service_group.getAll', 'format':'json'}
        try:
            response = requests.get(self.rest_api, params = service_group_params)
            data = json.loads(response.text)

            for value in data['service_group_list']:
                self.service_group_list.append(value['name'])
        except KeyError:
            print "ERROR: Unable to get service groups info from %s" % self.rest_api
            sys.exit(2)
    
        # Get all servers the from Load Balancer. Data will be used to verify parameters 
        # passed are in the Load Balancer.
        server_list_params = {'session_id':self.session_id, 'method':'slb.server.getAll', 'format':'json'}
    
        try:
            response = requests.get(self.rest_api, params = server_list_params)
            data = json.loads(response.text)

            for value in data['server_list']:
                self.server_list.append(value['name'])
        except KeyError:
            print "ERROR: Unable to get server list from %s" % self.rest_api
            sys.exit(2)

    def verify_host_in_lb(self):
        # Verify the host parameter passed is in the Load Balancer.
        hostname_list = self.hostname.split(',')
        for server in hostname_list:  
            if server not in self.server_list:
                print "ERROR: Host %s not found in load balancer inventory. Unable to %s host(s)" % (server, self.status)
                sys.exit(2)

    def verify_service_in_lb(self):
        # Verify the service_group parameter passed is in the Load Balancer.
            if self.service_group not in self.service_group_list:
                print "ERROR: Service group %s not found in load balancer inventory. Unable to %s host(s)" % (self.service_group, self.status)
                sys.exit(2)

    def update_server(self):
        # Update the host(s) status on the Load Balancer.
        # Convert the self.status to a numeric value to pass
        if self.status == 'disable':
            self.status = 1
        if self.status == 'enable':
            self.status = 0

        # Get all server from service_group. 
        service_group_members = []
        service_group_params = {'session_id':self.session_id, 'method':'slb.service_group.search', 'name':self.service_group, 'format':'json'}

        try:
            response = requests.get(self.rest_api, params = service_group_params)
            data = json.loads(response.text)

            for member in data['service_group']['member_list']:
                service_group_members.append (member['server'])        
        except KeyError:
            print "ERROR: Unable to get virtual server info from %s" % self.rest_api

        # Verify host(s) are in the service group.
        hostname_list = self.hostname.split(',')
        for server in hostname_list:  
            if server not in service_group_members:  
                print "ERROR: %s not found in service group %s. Unable to %s host(s)" % (server, self.service_group, self.status)
                sys.exit(2)

        # The slb.server_group_member.update requires port, priority, template and to be passed so I get the current values from the Load Balancer
        # so they are not overwritten.
        hostname_list = self.hostname.split(',')
        for server in hostname_list:
            server_data_params = {'session_id':self.session_id, 'method':'slb.server.search', 'name':server, 'format':'json'}
    
            try:
                response = requests.get(self.rest_api, params = server_data_params)
                data = json.loads(response.text)
           
                for element in data['server']['port_list']:
                    if element['port_num'] == int(self.port):
                        member_update_params = { 
                            'session_id': self.session_id,
                            'method': 'slb.service_group.member.update',
                            'name': self.service_group,
                            'server': server,
                            'status': self.status,
                            'port': self.port,
                            'priority': element['weight'],
                            'template': element['template'],
                            'format':'json'
                        } 

            except KeyError:
                print "ERROR: Unable to get server info from %s" % self.rest_api

            response = requests.get(self.rest_api, params = member_update_params)
            data = json.loads(response.text)

            if data['response']['status'] == 'fail':
                print "ERROR: Unable to disable host: %s" % data['response']['err']['msg'] 
                sys.exit(2)
            else:
                if self.status == int('1'):
                    self.status = 'Disabled'
                if self.status == int('0'):
                    self.status = 'Enabled'

                print "SUCCESS: %s %s on %s" % (self.status, server, self.service_group)


lb_update = A10Jenkins()
lb_update.authenticate()
lb_update.get_a10_data()
lb_update.verify_host_in_lb() 
lb_update.verify_service_in_lb()
lb_update.update_server()
