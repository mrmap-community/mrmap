#Installation instructions for debian 10
> tested on Debian GNU/Linux 10 (buster) with 
> * python 3.7.3 
> * pip 20.0.2
> * Docker version 19.03.8, build afacb8b7f0
> * pip installed docker-compose version 1.25.4, build unknown

##Install dependencies:
```bash
sudo apt install libcurl4-openssl-dev libssl-dev python3.7-dev gdal-bin virtualenv
```

##Install docker engine - community:

###Add apt repo
1. Install packages to allow apt to use a repository over HTTPS:

       sudo apt-get install \
           apt-transport-https \
           ca-certificates \
           curl \
           gnupg2 \
           software-properties-common

1. Add Docker’s official GPG key:

       curl -fsSL https://download.docker.com/linux/debian/gpg | sudo apt-key add -

   Verify that you now have the key with the fingerprint 9DC8 5822 9FC7 DD38 854A E2D8 8D81 803C 0EBF CD88, by searching for the last 8 characters of the fingerprint.

       sudo apt-key fingerprint 0EBFCD88

       pub   4096R/0EBFCD88 2017-02-22
             Key fingerprint = 9DC8 5822 9FC7 DD38 854A  E2D8 8D81 803C 0EBF CD88
       uid                  Docker Release (CE deb) <docker@docker.com>
       sub   4096R/F273FCD8 2017-02-22

1. Use the following command to set up the stable repository.

       sudo add-apt-repository \
          "deb [arch=amd64] https://download.docker.com/linux/debian \
          $(lsb_release -cs) \
          stable"


### Install Docker Engine
1. Update the apt package index.

       sudo apt-get update

1. Install the latest version of Docker Engine - Community and containerd, or go to the next step to install a specific version:

       sudo apt-get install docker-ce docker-ce-cli containerd.io

1. (Optional) Configure proxy
      * add new file /etc/systemd/system/docker.service.d/http-proxy.conf with following content:
   
       [Service]
       Environment="HTTP_PROXY=http://user:password@proxy:port"
       Environment="HTTPS_PROXY=http://user:password@proxy:port"
       
1. Verify that Docker Engine

       sudo docker run hello-world

1. Add your user to group docker:

       sudo usermod -aG docker {username}

   > after this command your system needs a restart for the changes to take effect

##Install docker-compose
> run this commands in your python [virtual env](https://docs.python.org/3/tutorial/venv.html) which you has already configured for this project.

1. install docker-compose with pip

        pip install docker-compose

1. check version:

        docker-compose --version
        
   result should be:
    
        docker-compose version 1.25.4, build unknown
