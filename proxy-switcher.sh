#!/bin/bash

sudo -v -p "Please enter you admin password: "

function setup {
	echo -e "\e[32mSet-up the proxy:\e[0m ${proxy}"
	echo "export http_proxy=\"http://${proxy}\"" | sudo tee /etc/bash.bashrc -a
	echo "export https_proxy=\"http://${proxy}\"" | sudo tee /etc/bash.bashrc -a
	echo "export HTTP_PROXY=\"http://${proxy}\"" | sudo tee /etc/bash.bashrc -a
	echo "export HTTPS_PROXY=\"http://${proxy}\"" | sudo tee /etc/bash.bashrc -a
	echo "Acquire::http::Proxy \"http://${proxy}\";" | sudo tee /etc/apt/apt.conf.d/proxy.conf -a

	if [[ -f /usr/share/applications/google-chrome.desktop ]]
	then
		sudo sed -i "s_Exec=/opt/google/chrome/google-chrome %U_Exec=/opt/google/chrome/google-chrome %U --proxy-server=${proxy}_" /usr/share/applications/google-chrome.desktop
	fi
	export http_proxy="http://${proxy}"
	export https_proxy="http://${proxy}"
	export HTTP_PROXY="http://${proxy}"
	export HTTPS_PROXY="http://${proxy}"

	if  [ -x "$(command -v git)" ]; then
		git config --global http.proxy "http://${proxy}"
		git config --global https.proxy "http://${proxy}"
	fi

	if  [ -x "$(command -v npm)" ]; then
		npm config set proxy "http://${proxy}" --global 
		npm config set https-proxy "http://${proxy}"  --global 
	fi

	if  [ -x "$(command -v yarn)" ]; then
		yarn config set proxy "http://${proxy}"
		yarn config set https-proxy "http://${proxy}"  
	fi
	if [ -x "$(command -v docker)" ]; then
		sudo mkdir /etc/systemd/system/docker.service.d
		sudo tee -a /etc/systemd/system/docker.service.d/http-proxy.conf <<EOF
[Service]
Environment="HTTP_PROXY=http://${proxy}/"
Environment="HTTPS_PROXY=http://${proxy}/"
Environment="FTP_PROXY=http://${proxy}/"
Environment="NO_PROXY=localhost,127.0.0.1,localaddress,.localdomain.com"	
EOF

		mkdir ~/.docker			
		tee -a ~/.docker/config.json <<EOF
{
 "proxies": {
  "default": {
   "httpProxy": "http://${proxy}",
   "httpsProxy": "http://${proxy}",
   "noProxy": "localhost"
  }
 }
}
EOF

		sudo systemctl daemon-reload
		sudo service docker restart
	fi

}

function remove {
	echo -e "\e[32mRemove the proxy\e[0m"
	sudo sed -i '/export http_proxy=/d' /etc/bash.bashrc
	sudo sed -i '/export https_proxy=/d' /etc/bash.bashrc
	sudo sed -i '/export HTTP_PROXY=/d' /etc/bash.bashrc
	sudo sed -i '/export HTTPS_PROXY=/d' /etc/bash.bashrc

	if [[ -f /etc/apt/apt.conf.d/proxy.conf ]]
	then
		sudo rm /etc/apt/apt.conf.d/proxy.conf
	fi
	if [[ -f /usr/share/applications/google-chrome.desktop ]]
	then
		sudo sed -i "s_Exec=/opt/google/chrome/google-chrome %U --proxy-server=.*_Exec=/opt/google/chrome/google-chrome %U_" /usr/share/applications/google-chrome.desktop
	fi

	unset http_proxy
	unset https_proxy
	unset HTTP_PROXY
	unset HTTPS_PROXY

	if  [ -x "$(command -v git)" ]; then
		git config --global http.proxy ""
		git config --global https.proxy ""
	fi

	if  [ -x "$(command -v npm)" ]; then
		npm config rm proxy
		npm config rm https-proxy
		npm config --global rm proxy
		npm config --global rm https-proxy
	fi

	if  [ -x "$(command -v yarn)" ]; then
		yarn config set proxy ""
		yarn config set https-proxy ""  
	fi

	if [ -x "$(command -v docker)" ];then
		if [ -f /etc/systemd/system/docker.service.d/http-proxy.conf ]; then
		 sudo rm /etc/systemd/system/docker.service.d/http-proxy.conf
		 sudo systemctl daemon-reload
		 sudo service docker restart
		fi
		if [ -x "$(command -v jq)" ]; then
			if [ -f ~/.docker/config.json ]; then
				cat ~/.docker/config.json | jq 'del(.proxies)' | tee ~/.docker/config.json
			fi
		else
			echo "You should install jq for handling json files. Run sudo apt install -y jq"
		fi
	fi
}

if [[ $1 != "" ]]
then
	proxy=$1
	remove
	setup
else
	remove
fi
