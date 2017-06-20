#!/usr/bin/env python

# Copyright 2017 Univa Corporation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


from common_utils import needs_config
from common_utils import needs_setup
from common_utils import needs_cleanup

from urb.adapters.adapter_manager import AdapterManager

@needs_setup
def test_setup():
    pass

@needs_config
def test_constructor():
    adapter_manager = AdapterManager.get_instance()
    assert isinstance(adapter_manager, AdapterManager)

@needs_cleanup
def test_cleanup():
    pass

# Testing
if __name__ == '__main__':
    pass
