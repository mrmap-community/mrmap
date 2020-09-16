#!bin/bash
installation_folder="/opt/"

check_django_settings(){
   missing_items=()

   cd /tmp/
   dottedname=`echo $1 | sed s/"\/"/"."/g`
   rm $dottedname
   wget https://git.osgeo.org/gitea/GDI-RP/MrMap/raw/branch/pre_master/$1 -O $dottedname

   while IFS="" read -r p || [ -n "$p" ]
     do
        h=`printf '%s\n' "$p" | cut -d = -f 1`
        h_full=`printf '%s\n' "$p"`
        if ! grep -Fq "$h" ${installation_folder}/MrMap/$1
        then
            missing_items+=("$h_full")
         fi

   done < /tmp/$dottedname

   if [ ${#missing_items[@]} -ne 0 ]; then
     echo "The following items are present in the masters $1 but are missing in your local $1"
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
echo "!!!!!!!!!!!!!!!!!!!!!!!!!!
Checking MrMap/settings.py
!!!!!!!!!!!!!!!!!!!!!!!!!!"
check_django_settings "MrMap/settings.py"

echo "!!!!!!!!!!!!!!!!!!!!!!!!!!
Checking service/settings.py
!!!!!!!!!!!!!!!!!!!!!!!!!!"
check_django_settings "service/settings.py"

echo "!!!!!!!!!!!!!!!!!!!!!!!!!!
Checking sub settings
!!!!!!!!!!!!!!!!!!!!!!!!!!"
check_django_settings "MrMap/sub_settings/dev_settings.py"
check_django_settings "MrMap/sub_settings/db_settings.py"
check_django_settings "MrMap/sub_settings/django_settings.py"
check_django_settings "MrMap/sub_settings/logging_settings.py"


cd ${installation_folder}MrMap/
echo "Backing up Django Configs"
cp -av ${installation_folder}MrMap/MrMap/settings.py /tmp/settings.py_$(date +"%m_%d_%Y")
cp -av ${installation_folder}MrMap/service/settings.py /tmp/service_settings.py_$(date +"%m_%d_%Y")
cp -av ${installation_folder}MrMap/MrMap/sub_settings/dev_settings.py /tmp/dev_settings.py_$(date +"%m_%d_%Y")
cp -av ${installation_folder}MrMap/MrMap/sub_settings/db_settings.py /tmp/db_settings.py_$(date +"%m_%d_%Y")
cp -av ${installation_folder}MrMap/MrMap/sub_settings/django_settings.py /tmp/dj_settings.py_$(date +"%m_%d_%Y")
cp -av ${installation_folder}MrMap/MrMap/sub_settings/logging_settings.py /tmp/log_settings.py_$(date +"%m_%d_%Y")

git reset --hard
git pull

echo "Restoring Django Configs"
cp -av /tmp/settings.py_$(date +"%m_%d_%Y") ${installation_folder}MrMap/MrMap/settings.py
cp -av /tmp/service_settings.py_$(date +"%m_%d_%Y") ${installation_folder}MrMap/service/settings.py
cp -av /tmp/dev_settings.py_$(date +"%m_%d_%Y") ${installation_folder}MrMap/MrMap/sub_settings/dev_settings.py
cp -av /tmp/db_settings.py_$(date +"%m_%d_%Y") ${installation_folder}MrMap/MrMap/sub_settings/db_settings.py
cp -av /tmp/dj_settings.py_$(date +"%m_%d_%Y") ${installation_folder}MrMap/MrMap/sub_settings/django_settings.py
cp -av /tmp/log_settings.py_$(date +"%m_%d_%Y") ${installation_folder}MrMap/MrMap/sub_settings/logging_settings.py

#uncomment if you have dropped db
#find ${installation_folder}MrMap -path "*/migrations/*.py" -not -name "__init__.py" -delete
#find ${installation_folder}MrMap -path "*/migrations/*.pyc"  -delete
#find ${installation_folder}MrMap -name "*migrations*" | xargs rm -r

python -m pip install -r requirements.txt
rm -r ${installation_folder}MrMap/static
python manage.py collectstatic
python manage.py compilemessages
python manage.py makemigrations
python manage.py migrate

# uncomment this if you have dropped the db
#python manage.py makemigrations service structure editor monitoring users csw
#python manage.py migrate service structure editor monitoring users csw
#python manage.py makemigrations
#python manage.py migrate


systemctl restart uwsgi
/etc/init.d/nginx restart

echo "Update Complete"
