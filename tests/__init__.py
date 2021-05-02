import os
import sys

project_path = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
sub_path = os.path.join(project_path, 'hdhr_monitor_disk_space')
print(project_path)
print(sub_path)
sys.path.append(sub_path)
