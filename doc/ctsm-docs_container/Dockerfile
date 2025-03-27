###################################################################
# A base linux install + packages for building CTSM documentation #
###################################################################

FROM almalinux:9.5

# First, we upate the default packages and install some other necessary ones - while this may give
# some people updated versions of packages vs. others, these differences should not be numerically
# important or affect run-time behavior (eg, a newer Bash version, or perl-XML-LibXML version).

RUN yum -y update
RUN yum -y install epel-release
RUN yum -y install git sudo
RUN yum -y install python3 pip
RUN yum -y install git-lfs
RUN pip3 install rst2pdf sphinx sphinxcontrib-programoutput
RUN pip3 install sphinx-rtd-theme
RUN pip3 install sphinx_mdinclude
RUN dnf config-manager --set-enabled crb
RUN dnf -y update
RUN dnf install -y blas-devel lapack-devel
RUN ln -s /usr/bin/python3 /usr/bin/python
RUN echo '/usr/local/lib' > /etc/ld.so.conf.d/local.conf
RUN ldconfig
RUN yum clean all

RUN groupadd escomp && \
    useradd -c 'ESCOMP User' -d /home/user -g escomp -m -s /bin/bash user && \
    echo 'export USER=$(whoami)' >> /etc/profile.d/escomp.sh && \
    echo 'export PS1="[\u@escomp \W]\$ "' >> /etc/profile.d/escomp.sh && \
    echo 'user ALL=(ALL) NOPASSWD: ALL' >> /etc/sudoers.d/escomp

ENV SHELL=/bin/bash \
    LANG=C.UTF-8  \
    LC_ALL=C.UTF-8

USER user
WORKDIR /home/user
CMD ["/bin/bash", "-l"]
