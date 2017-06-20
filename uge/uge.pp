# Install and configure UGE

package { "numactl":
  ensure => "installed"
}

group { 'uge':
    ensure => 'present', 
}

group { 'docker':
    ensure => 'present', 
}

user { 'uge': 
    gid => 'uge',
    groups => ['docker'],
    managehome => true,
    comment => 'UGE user',
    require => [Group['uge'], Group['docker']]
}

file { '/opt/uge':
    ensure => 'directory',
    owner =>  'uge',
    group =>  'uge',
    require => User['uge']
}

exec { "unbundle_uge_common":
    command => "/bin/tar xzvf /scratch/urb/uge/*common*.tar.gz -C /opt/uge",
    creates => "/opt/uge/lib/jgdi.jar",
    require => File['/opt/uge'],
}

exec { "unbundle_uge_bin":
    command => "/bin/tar xzvf /scratch/urb/uge/*bin*.tar.gz -C /opt/uge",
    creates => "/opt/uge/utilbin",
    require => File['/opt/uge'],
}

exec { "install_qmaster":
    cwd     => "/opt/uge",
    command => "/opt/uge/inst_sge -m -auto /scratch/urb/uge/inst_template.conf",
    creates  => "/opt/uge/default/spool/qmaster",
    require => [Exec['unbundle_uge_common'],Exec['unbundle_uge_bin']]
}

service { "sgemaster.p6444":
    ensure => true,
    require => [Exec['install_qmaster']]
}

exec { "install_execd":
    cwd     => "/opt/uge",
    command => "/opt/uge/inst_sge -x -auto /scratch/urb/uge/inst_template.conf",
    creates  => "/opt/uge/default/spool/head",
    require => [Exec['install_qmaster'], Package['numactl']]
}

service { "sgeexecd.p6444":
    ensure => true,
    require => [Exec['install_execd']]
}

file { "/etc/profile.d/uge.sh":
    ensure => "link",
    target => "/opt/uge/default/common/settings.sh",
    require => Exec['install_qmaster']
}

exec { "remove_load_thresh_from_all_queue":
    command => "/bin/bash -c '. /opt/uge/default/common/settings.sh; qconf -rattr queue load_thresholds NONE all.q'",
    unless  => "/bin/bash -c '. /opt/uge/default/common/settings.sh; qconf -sq all.q | grep \"^load_thresholds.*NONE\"'",
    require => Exec['install_qmaster']
}

exec { "shell_all_queue":
    command => "/bin/bash -c '. /opt/uge/default/common/settings.sh; qconf -rattr queue shell /bin/bash all.q'",
    unless  => "/bin/bash -c '. /opt/uge/default/common/settings.sh; qconf -sq all.q | grep \"^shell.*/bin/bash\"'",
    require => Exec['install_qmaster']
}

exec { "configure_all_slots":
    command => "/bin/bash -c '. /opt/uge/default/common/settings.sh; qconf -mattr queue slots 10 all.q@head.private'",
    unless  => "/bin/bash -c '. /opt/uge/default/common/settings.sh; qconf -sq all.q | grep \"^slots.*10\"'",
    require => [Exec['install_execd']],
}

exec { "job_class":
    command => "/bin/bash -c '. /opt/uge/default/common/settings.sh; qconf -sjc template | sed \"s|^jcname.*\$|jcname         URBDefault|;s|^CMDNAME.*\$|CMDNAME         /scratch/urb/urb-core/etc/urb-executor-runner|\" > /tmp/URBDefault.jc; qconf -Ajc /tmp/URBDefault.jc'",
    unless  => "/bin/bash -c '. /opt/uge/default/common/settings.sh; qconf -sjc URBDefault",
    require => Exec['install_qmaster']
}

exec { "uge_manager":
    command => "/bin/bash -c '. /opt/uge/default/common/settings.sh; qconf -am vagrant'",
    unless  => "/bin/bash -c '. /opt/uge/default/common/settings.sh; qconf -sm | grep vagrant'",
    require => [Exec['install_execd']],
}
