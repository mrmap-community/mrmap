WITH RECURSIVE generate_data AS (
    SELECT 4000002 AS id,  -- Starte bei 4000001, um Konflikte mit existierenden IDs zu vermeiden
           'file_' || floor(random() * 1000) || '.txt' AS md_metadata_file,  -- Zufälliger Dateiname
           (random() > 0.5) AS re_schedule,  -- Zufälliger Boolean-Wert
           CASE WHEN random() > 0.8 THEN 'Error in import' ELSE '' END AS import_error,  -- Leerer String statt NULL
           150 AS job_id,  -- job_id immer 100
           INTERVAL '1 hour' + (random() * INTERVAL '4 hours') AS download_duration,  -- Zufällige Dauer
           'http://example.com/file' || floor(random() * 1000) AS requested_url,  -- Zufällige URL
           NOW() - (random() * INTERVAL '30 days') AS request_id,  -- Zufälliger Zeitstempel in den letzten 30 Tagen
           (random() > 0.2) AS has_import_error  -- Zufälliger Boolean-Wert für Importfehler
    UNION ALL
    SELECT id + 1,
           'file_' || floor(random() * 1000) || '.txt',
           (random() > 0.5),
           CASE WHEN random() > 0.8 THEN 'Error in import' ELSE '' END,
           150,
           INTERVAL '1 hour' + (random() * INTERVAL '4 hours'),
           'http://example.com/file' || floor(random() * 1000),
           NOW() - (random() * INTERVAL '30 days'),
           (random() > 0.2)
    FROM generate_data
    WHERE id < 8000001  -- Erzeuge 1 Million Datensätze (startet bei 4000001 bis 8000001)
)
INSERT INTO registry_temporarymdmetadatafile 
(id, md_metadata_file, re_schedule, import_error, job_id, download_duration, requested_url, request_id, has_import_error)
SELECT id, md_metadata_file, re_schedule, import_error, job_id, download_duration, requested_url, request_id, has_import_error
FROM generate_data;