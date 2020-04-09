#!bin/bash
installation_folder="/opt/"

check_django_settings(){
   missing_items=()

   rm /tmp/settings.py
   cd /tmp/
   wget https://git.osgeo.org/gitea/GDI-RP/MapSkinner/raw/branch/pre_master/MapSkinner/settings.py

   while IFS="" read -r p || [ -n "$p" ]
     do
        h=`printf '%s\n' "$p" | cut -d = -f 1`
        h_full=`printf '%s\n' "$p"`
        if ! grep -Fq "$h" ${installation_folder}/MapSkinner/MapSkinner/settings.py
        then
            missing_items+=("$h_full")
         fi

   done < /tmp/settings.py

   if [ ${#missing_items[@]} -ne 0 ]; then
     echo "The following items are present in the masters settings.py but are missing in your local settings.py!"
     printf '%s\n' "${missing_items[@]}"

     while true; do
         read -p "Do you want to continue y/n?" yn
         case $yn in
             [Yy]* ) break;;
             [Nn]* ) exit;break;;
             * ) echo "Please answer yes or no.";;
         esac
     done
  fi

}

custom_update(){

  if [ -e ${installation_folder}"custom_files.txt" ];then
      if [ "$1" == "save" ];then
        input="${installation_folder}/custom_files.txt"
        while IFS= read -r line
        do
          directory=`echo $line | cut -d / -f 3-`
          filename=`echo $line | cut -d / -f 3- | rev | cut -d / -f -1 | rev`
          directory=${directory%$filename}

          mkdir -p /tmp/custom_files/$directory
          cp -a $line /tmp/custom_files/$directory
        done < "$input"
      fi

      if [ "$1" == "restore" ];then
          cp -a /tmp/custom_files/* ${installation_folder}
      fi
    fi
}

check_django_settings
cd ${installation_folder}MapSkinner/
echo "Backing up Django Configs"
cp -av ${installation_folder}MapSkinner/MapSkinner/settings.py /tmp/settings.py_$(date +"%m_%d_%Y")
cp -av ${installation_folder}MapSkinner/service/settings.py /tmp/service_settings.py_$(date +"%m_%d_%Y")

git reset --hard
git pull

echo "Restoring Django Configs"
cp -av /tmp/settings.py_$(date +"%m_%d_%Y") ${installation_folder}MapSkinner/MapSkinner/settings.py
cp -av /tmp/service_settings.py_$(date +"%m_%d_%Y") ${installation_folder}MapSkinner/service/settings.py

python -m pip install -r requirements.txt
rm -r ${installation_folder}MapSkinner/static
python manage.py collectstatic
python manage.py compilemessages

systemctl restart uwsgi
/etc/init.d/nginx restart

echo "Update Complete"
