--create table registry_harvesteddatasetmetadata_partition (like registry_harvesteddatasetmetadatarelation) partition by list(collecting_state);
--create table registry_harvesteddatasetmetadata_new partition of registry_harvesteddatasetmetadata_partition for values in ('new');
--create table registry_harvesteddatasetmetadata_updated partition of registry_harvesteddatasetmetadata_partition for values in ('updated');
--create table registry_harvesteddatasetmetadata_duplicated partition of registry_harvesteddatasetmetadata_partition for values in ('duplicated');
--create table registry_harvesteddatasetmetadata_existing partition of registry_harvesteddatasetmetadata_partition for values in ('existing');
--insert into registry_harvesteddatasetmetadata_partition select * from registry_harvesteddatasetmetadatarelation;

--create table registry_harvesteddatasetmetadata_partition (like registry_harvesteddatasetmetadatarelation) partition by list(collecting_state);
--create table registry_harvesteddatasetmetadata_new partition of registry_harvesteddatasetmetadata_partition for values in ('new');
--create table registry_harvesteddatasetmetadata_updated partition of registry_harvesteddatasetmetadata_partition for values in ('updated');
--create table registry_harvesteddatasetmetadata_duplicated partition of registry_harvesteddatasetmetadata_partition for values in ('duplicated');
--create table registry_harvesteddatasetmetadata_existing partition of registry_harvesteddatasetmetadata_partition for values in ('existing');
--insert into registry_harvesteddatasetmetadata_partition select * from registry_harvesteddatasetmetadatarelation;

--create table registry_temporarymdmetadatafile_partition (like registry_temporarymdmetadatafile) partition by list(has_import_error);
--create table registry_temporarymdmetadatafile_has_errors partition of registry_temporarymdmetadatafile_partition for values in (true);
--create table registry_temporarymdmetadatafile_has_no_errors partition of registry_temporarymdmetadatafile_partition for values in (false);
--insert into registry_temporarymdmetadatafile_partition select * from registry_temporarymdmetadatafile;


-- HINT: denke an die index erstellung in der partitionstabelle!!


explain analyze WITH "dataset_sums" AS (
        SELECT "registry_harvesteddatasetmetadata_partition"."harvesting_job_id",
               COALESCE(SUM(CASE WHEN "registry_harvesteddatasetmetadata_partition"."collecting_state" = 'new' THEN 1 ELSE 0 END), 0)  AS "new_dataset_metadata_count",
               COALESCE(SUM(CASE WHEN "registry_harvesteddatasetmetadata_partition"."collecting_state" = 'updated' THEN 1 ELSE 0 END), 0)  AS "updated_dataset_metadata_count",
               COALESCE(SUM(CASE WHEN "registry_harvesteddatasetmetadata_partition"."collecting_state" = 'existing' THEN 1 ELSE 0 END), 0)  AS "existing_dataset_metadata_count",
               COALESCE(SUM(CASE WHEN "registry_harvesteddatasetmetadata_partition"."collecting_state" = 'duplicated' THEN 1 ELSE 0 END), 0)  AS "duplicated_dataset_metadata_count",
               COALESCE(SUM("registry_harvesteddatasetmetadata_partition"."download_duration"), '0:00:00'::interval) AS "fetch_record_duration",
               COALESCE(SUM("registry_harvesteddatasetmetadata_partition"."processing_duration"), '0:00:00'::interval) AS "md_metadata_file_to_db_duration"
          FROM "registry_harvesteddatasetmetadata_partition"
         GROUP BY "registry_harvesteddatasetmetadata_partition"."harvesting_job_id"
       ),
       "service_sums" AS (
        SELECT "registry_harvestedservicemetadata_partition"."harvesting_job_id",
        	   COALESCE(SUM(CASE WHEN "registry_harvestedservicemetadata_partition"."collecting_state" = 'new' THEN 1 ELSE 0 END), 0) AS "new_service_metadata_count",       
               COALESCE(SUM(CASE WHEN "registry_harvestedservicemetadata_partition"."collecting_state" = 'updated' THEN 1 ELSE 0 END), 0) AS "updated_service_metadata_count",       
        	   COALESCE(SUM(CASE WHEN "registry_harvestedservicemetadata_partition"."collecting_state" = 'existing' THEN 1 ELSE 0 END), 0) AS "existing_service_metadata_count",       
        	   COALESCE(SUM(CASE WHEN "registry_harvestedservicemetadata_partition"."collecting_state" = 'duplicated' THEN 1 ELSE 0 END), 0) AS "duplicated_service_metadata_count",       
			   COALESCE(SUM("registry_harvestedservicemetadata_partition"."download_duration"), '0:00:00'::interval) AS "fetch_record_duration",
               COALESCE(SUM("registry_harvestedservicemetadata_partition"."processing_duration"), '0:00:00'::interval) AS "md_metadata_file_to_db_duration"
          FROM "registry_harvestedservicemetadata_partition"
         GROUP BY "registry_harvestedservicemetadata_partition"."harvesting_job_id"
       ),
       "unhandled_records_cte" AS (
        SELECT "registry_temporarymdmetadatafile_partition"."job_id",
        	   COALESCE(SUM(CASE WHEN NOT ("registry_temporarymdmetadatafile_partition"."has_import_error" = true) THEN 1 ELSE 0 END), 0) AS "import_error_count",
    		   COALESCE(SUM(CASE WHEN "registry_temporarymdmetadatafile_partition"."has_import_error" = false THEN 1 ELSE 0 END), 0) AS "unhandled_records_count",
    		   SUM("registry_temporarymdmetadatafile_partition"."id") AS "records_count"
          FROM "registry_temporarymdmetadatafile_partition"
         GROUP BY "registry_temporarymdmetadatafile_partition"."job_id"
       ) SELECT "registry_harvestingjob"."id",
       "registry_harvestingjob"."service_id",
       "registry_harvestingjob"."max_step_size",
       "registry_harvestingjob"."background_process_id",
       "registry_harvestingjob"."harvest_datasets",
       "registry_harvestingjob"."harvest_services",
       "registry_harvestingjob"."total_records",
       ("dataset_sums"."fetch_record_duration" + "service_sums"."fetch_record_duration") AS "fetch_record_duration",
       ("dataset_sums"."md_metadata_file_to_db_duration" + "service_sums"."md_metadata_file_to_db_duration") AS "md_metadata_file_to_db_duration",
       COALESCE("dataset_sums"."new_dataset_metadata_count", 0) AS "new_dataset_metadata_count",
       COALESCE("dataset_sums"."updated_dataset_metadata_count", 0) AS "updated_dataset_metadata_count",
       COALESCE("dataset_sums"."existing_dataset_metadata_count", 0) AS "existing_dataset_metadata_count",
       COALESCE("dataset_sums"."duplicated_dataset_metadata_count", 0) AS "duplicated_dataset_metadata_count",
       COALESCE("service_sums"."new_service_metadata_count", 0) AS "new_service_metadata_count",
       COALESCE("service_sums"."updated_service_metadata_count", 0) AS "updated_service_metadata_count",
       COALESCE("service_sums"."existing_service_metadata_count", 0) AS "existing_service_metadata_count",
       COALESCE("service_sums"."duplicated_service_metadata_count", 0) AS "duplicated_service_metadata_count",
       CEILING(("registry_harvestingjob"."total_records" / "registry_harvestingjob"."max_step_size")) AS "download_tasks_count",
       ((CEILING(("registry_harvestingjob"."total_records" / "registry_harvestingjob"."max_step_size")) + "registry_harvestingjob"."total_records") + 1) AS "total_steps",
       COALESCE("unhandled_records_cte"."unhandled_records_count", 0) AS "unhandled_records_count",
       CASE WHEN UPPER("notify_backgroundprocess"."phase"::text) LIKE UPPER('%completed%')                                    THEN ((CEILING(("registry_harvestingjob"."total_records" / "registry_harvestingjob"."max_step_size")) + "registry_harvestingjob"."total_records") + 1)
            WHEN UPPER("notify_backgroundprocess"."phase"::text) LIKE UPPER('%Harvesting is running...%')                     THEN (1 + CEILING(("unhandled_records_cte"."records_count" / "registry_harvestingjob"."max_step_size")))
            WHEN UPPER("notify_backgroundprocess"."phase"::text) LIKE UPPER('%parse and store ISO Metadatarecords to db...%') THEN (((1 + CEILING(("registry_harvestingjob"."total_records" / "registry_harvestingjob"."max_step_size"))) + "registry_harvestingjob"."total_records") - "unhandled_records_cte"."records_count")
            ELSE 0
             END AS "done_steps",
       CASE WHEN (NOT ("notify_backgroundprocess"."phase" = 'abort') AND "notify_backgroundprocess"."done_at" IS NOT NULL) THEN 100.0
            ELSE CASE WHEN ((CEILING(("registry_harvestingjob"."total_records" / "registry_harvestingjob"."max_step_size")) + "registry_harvestingjob"."total_records") + 1) > 0 THEN ROUND(((((CASE WHEN UPPER("notify_backgroundprocess"."phase"::text) LIKE UPPER('%completed%') THEN ((CEILING(("registry_harvestingjob"."total_records" / "registry_harvestingjob"."max_step_size")) + "registry_harvestingjob"."total_records") + 1) WHEN UPPER("notify_backgroundprocess"."phase"::text) LIKE UPPER('%Harvesting is running...%') THEN (1 + CEILING(("unhandled_records_cte"."records_count" / "registry_harvestingjob"."max_step_size"))) WHEN UPPER("notify_backgroundprocess"."phase"::text) LIKE UPPER('%parse and store ISO Metadatarecords to db...%') THEN (((1 + CEILING(("registry_harvestingjob"."total_records" / "registry_harvestingjob"."max_step_size"))) + "registry_harvestingjob"."total_records") - "unhandled_records_cte"."records_count") ELSE 0 END * 1.0) / ((CEILING(("registry_harvestingjob"."total_records" / "registry_harvestingjob"."max_step_size")) + "registry_harvestingjob"."total_records") + 1)) * 100.0))::numeric(1000, 15), 0) ELSE 0.0 END
             END AS "progress",
       COALESCE("unhandled_records_cte"."import_error_count", 0) AS "import_error_count"
  FROM "registry_harvestingjob"
  LEFT OUTER JOIN "dataset_sums"
    ON "registry_harvestingjob"."id" = ("dataset_sums"."harvesting_job_id")
  LEFT OUTER JOIN "service_sums"
    ON "registry_harvestingjob"."id" = ("service_sums"."harvesting_job_id")
 INNER JOIN "notify_backgroundprocess"
    ON ("registry_harvestingjob"."background_process_id" = "notify_backgroundprocess"."id")
  LEFT JOIN "unhandled_records_cte"
    ON "registry_harvestingjob"."id" = ("unhandled_records_cte"."job_id")
    GROUP BY "registry_harvestingjob"."id",
          8,
          9,
          10,
          11,
          12,
          13,
          14,
          15,
          16,
          17,
          18,
          19,
          20,
          "notify_backgroundprocess"."phase", 
          ((1 + CEILING(("registry_harvestingjob"."total_records" / "registry_harvestingjob"."max_step_size"))) + "registry_harvestingjob"."total_records"),
          "notify_backgroundprocess"."done_at",
          "unhandled_records_cte"."records_count",
       23
 LIMIT 40