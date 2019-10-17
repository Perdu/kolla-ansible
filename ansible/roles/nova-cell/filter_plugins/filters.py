#!/usr/bin/python

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from jinja2.exceptions import TemplateRuntimeError
import re


class FilterModule(object):
    def filters(self):
        return {
            'extract_cell': self._extract_cell,
            'namespace_haproxy_for_cell': self._namespace_haproxy_for_cell,
        }

    def _extract_cell(self, list_cells_cli_output, cell_name):
        """Extract cell settings from nova_manage CLI

        This filter tries to extract the cell settings for the specified cell
        from the output of the command:
        nova-manage cell_v2 list_cells --verbose
        If the cell is not registered, nothing is returned.

        An example line from this command for a cell with no name looks like this:

        |  | 68a3f49e-27ec-422f-9e2e-2a4e5dc8291b | rabbit://openstack:password@1.2.3.4:5672 | mysql+pymysql://nova:password@1.2.3.4:3306/nova |  False   |  # noqa

        And for a cell with a name:

        | cell1 | 68a3f49e-27ec-422f-9e2e-2a4e5dc8291b | rabbit://openstack:password@1.2.3.4:5672 | mysql+pymysql://nova:password@1.2.3.4:3306/nova |  False   |  # noqa

        """
        # NOTE(priteau): regexp doesn't support passwords containing spaces
        p = re.compile(
            r'\| +(?P<cell_name>[^ ]+)? +'
            r'\| +(?!00000000-0000-0000-0000-000000000000)'
            r'(?P<cell_uuid>[0-9a-f\-]+) +'
            r'\| +(?P<cell_message_queue>[^ ]+) +'
            r'\| +(?P<cell_database>[^ ]+) +'
            r'\| +(?P<cell_disabled>[^ ]+) +'
            r'\|$')
        cells = []
        for line in list_cells_cli_output['stdout_lines']:
            match = p.match(line)
            if match:
                # If there is no cell name, we get None in the cell_name match
                # group. Use an empty string to match the default cell.
                match_cell_name = match.group('cell_name') or ""
                if match_cell_name == cell_name:
                    cells.append(match.groupdict())
        if len(cells) > 1:
            raise TemplateRuntimeError(
                "Cell: {} has duplicates. "
                "Manual cleanup required.".format(cell_name))
        return cells[0] if cells else None

    def _namespace_haproxy_for_cell(self, services, cell_name):
        """Add namespacing to HAProxy configuration for a cell.

        :param services: dict defining service configuration.
        :param cell_name: name of the cell, or empty if cell has no name.
        :returns: the services dict, with haproxy configuration modified to
            provide namespacing between cells.
        """

        def _namespace(name):
            # Backwards compatibility - no cell name suffix for cells without a
            # name.
            return "{}_{}".format(name, cell_name) if cell_name else name

        # Service name must be namespaced as haproxy-config uses this as the
        # config file name.
        services = {
            _namespace(service_name): service
            for service_name, service in services.items()
        }
        for service in services.values():
            if service.get('haproxy'):
                service['haproxy'] = {
                    _namespace(name): service['haproxy'][name]
                    for name in service['haproxy']
                }
        return services
