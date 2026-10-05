import { TranslationMessages } from "ra-core";

// @ts-ignore
const germanMessages: TranslationMessages = {
  updateReview: {
    "title": "Dienstaktualisierung prüfen",
    "job": "Aktualisierungsauftrag #%{id}",
    "needsReview": "Prüfung erforderlich",
    "resolved": "Prüfung abgeschlossen",
    "subtitle": "Die Aktualisierung wird automatisch fortgesetzt, sobald alle Änderungen geklärt sind.",
    "remaining": "%{count} Änderungen zu prüfen",
    "progress": "%{resolved} von %{total} geklärt",
    "tree": "Neue Layerstruktur",
    "findLayer": "Layer suchen",
    "changes": "Zu prüfende Änderungen",
    "pending": "Ausstehend",
    "all": "Alle",
    "added": "Neuer Layer",
    "modified": "Geänderter Layer",
    "unchanged": "Unveränderter Layer",
    "removed": "Entfernter Layer",
    "confirmed": "Bestätigt",
    "searchChanges": "Änderungen suchen",
    "noChanges": "Keine Änderungen entsprechen diesen Filtern.",
    "selectChange": "Wählen Sie eine Änderung zur Prüfung aus.",
    "current": "Aktueller Dienst",
    "incoming": "Eingehende Aktualisierung",
    "noMatch": "Kein zugeordneter Layer",
    "resolve": "Änderung klären",
    "resolveHelp": "Bestätigen Sie den eingehenden Layer oder ordnen Sie ihn einem bestehenden Layer zu. Ausstehende Änderungen halten die Aktualisierung an.",
    "mapExisting": "Bestehendem Layer zuordnen (optional)",
    "mapHelp": "Wählen Sie einen bestehenden Layer, um dessen Konfiguration zu erhalten. Ohne Auswahl wird ein neuer Layer hinzugefügt.",
    "confirm": "Änderung bestätigen",
    "savePending": "Als ausstehend speichern",
    "savedOnSubmit": "Entscheidungen werden beim Bestätigen oder Speichern gespeichert.",
    "mapping": "Layerzuordnung #%{id}",
    "loadError": "Die Layerstruktur konnte nicht geladen werden. Bitte versuchen Sie es erneut."
  },
  serviceShow: {
      featureTypeChanges: "Änderungen an Feature-Typen",
      harvestedChanges: "Änderungen an geharvesteten Datensätzen",
    overview: "Übersicht",
    details: "Dienstdetails",
    metadata: "Metadaten",
    capabilities: "GetCapabilities-URL",
    operationUrls: "Operations-URLs",
    layers: "Layer",
    featureTypes: "Feature-Typen",
    records: "Datensätze",
    proxy: "Proxy-Einstellungen",
    access: "Zugriffsregeln",
    monitoring: "Monitoring",
    updates: "Aktualisierungseinstellungen",
    harvesting: "Harvesting-Aktivität",
    schedules: "Harvesting-Zeitpläne",
    history: "Letzte Änderungen",
    empty: "Noch keine Einträge.",
    configure: "Verwalten",
    loadError: "Konfiguration konnte nicht geladen werden.",
    readOnly: "Diese Konfiguration ist schreibgeschützt.",
  },
  systemInfo: {
    "title": "Systeminformationen",
    "unavailable": "Systeminformationen sind nicht verfügbar.",
    "mrmapRelease": "MrMap-Version",
    "djangoVersion": "Django-Version",
    "pythonVersion": "Python-Version",
    "postgresqlVersion": "PostgreSQL-Version",
    "databaseName": "Datenbankname",
    "databaseSize": "Datenbankgröße",
    "celeryWorkerCount": "Anzahl der Celery-Worker",
    "redisUp": "Redis erreichbar",
    "systemTime": "Systemzeit"
  },
  systemStatus: {
      "checking": "Wird geprüft…",
      "viewDetails": "Details zum Systemstatus anzeigen",
    "title": "Systemstatus",
    "observed": "Beobachtet am",
    "stale": "Die Überwachungsdaten sind veraltet oder nicht verfügbar. Der aktuelle Zustand ist unbekannt.",
    "workers": "Celery-Worker",
    "beat": "Celery Beat",
    "redis": "Redis",
    "database": "PostgreSQL",
    "noObservation": "Keine aktuelle Beobachtung",
    "lastSeen": "Letztes Lebenszeichen",
    "unavailable": "Die Systemüberwachung ist nicht verfügbar.",
    "states": {
      "healthy": "In Ordnung",
      "down": "Gestoppt",
      "unknown": "Unbekannt",
      "degraded": "Eingeschränkt"
    }
  },
  ra: {
    list: {
      actions: "Aktionen",
    },
    action: {
      active: '%{name} aktivieren',
      add_filter: "Filter hinzufügen",
      add: "Neu",
      back: "Zurück",
      bulk_actions: "Ein Element ausgewählt |||| %{smart_count} Elemente ausgewählt",
      cancel: "Abbrechen",
      clear_array_input: "Liste löschen",
      clear_input_value: "Eingabe löschen",
      clone: "Klonen",
      confirm: "Bestätigen",
      create: "Erstellen",
      create_item: "%{item} erstellen",
      delete: "Löschen",
      deactive: '%{name} deaktivieren',
      edit: "Bearbeiten",
      export: "Exportieren",
      list: "Liste",
      refresh: "Neu laden",
      remove_filter: "Filter entfernen",
      remove_all_filters: "Alle Filter entfernen",
      remove: "Entfernen",
      save: "Speichern",
      search: "Suchen",
      select_all: "Alles auswählen",
      select_row: "Reihe auswählen",
      show: "Anzeigen",
      show_all: 'Zeige alle %{name}',
      sort: "Sortieren",
      undo: "Rückgängig machen",
      unselect: "Abwählen",
      expand: "Erweitern",
      close: "Schließen",
      open_menu: "Menü öffnen",
      close_menu: "Menü schließen",
      update: "Aktualisieren",
      move_up: "Nach oben",
      move_down: "Nach unten",
      open: "Öffnen",
      toggle_theme: "Theme wechseln",
      select_columns: "Spalten",
      mapviewer: 'Kartenbetrachter'
    },
    boolean: {
      true: "Ja",
      false: "Nein",
      null: ' '
    },
    page: {
      create: "%{name} erstellen",
      dashboard: "Dashboard",
      edit: "%{name} %{recordRepresentation}",
      error: "Etwas ist schiefgelaufen",
      list: "%{name}",
      loading: "Laden",
      not_found: "Nicht gefunden",
      show: "%{name} %{recordRepresentation}",
      empty: "Noch kein %{name}.",
      invite: "Neu erstellen?"
    },
    input: {
      file: {
        upload_several:
          "Dateien hier ablegen, oder zum Auswählen klicken.",
        upload_single: "Dateien hier ablegen, oder zum Auswählen klicken."
      },
      image: {
        upload_several:
          "Bilder hier ablegen, oder zum Auswählen klicken.",
        upload_single:
          "Bild hier ablegen, oder zum Auswählen klicken."
      },
      references: {
        all_missing: "Die Daten der Referenz können nicht gefunden werden.",
        many_missing:
          "Mindestens eine Referenz scheint nicht mehr verfügbar zu sein.",
        single_missing:
          "Die Referenz scheint nicht mehr verfügbar zu sein."
      },
      password: {
        toggle_visible: "Passwort verbergen",
        toggle_hidden: "Passwort einblenden"
      }
    },
    message: {
      about: "Über",
      are_you_sure: "Sind Sie sicher?",
      auth_error:
        "Bei der Validierung des Authentifizierungstokens ist ein Fehler aufgetreten.",
      bulk_delete_content:
        "Sicher, dass Sie %{name} löschen wollen? |||| Sicher, dass Sie diese %{smart_count} Elemente löschen wollen?",
      bulk_delete_title:
        "%{name} löschen |||| %{smart_count} %{name} löschen",
      bulk_update_content:
        "Sicher, dass Sie %{name} aktualisieren wollen? |||| Sicher, dass Sie %{smart_count} Elemente aktualisieren wollen?",
      bulk_update_title:
        "%{name} aktualisieren |||| %{smart_count} %{name} aktualisieren",
      clear_array_input: "Sicher, dass Sie die ganze Liste löschen wollen?",
      delete_content: "Sicher, dass Sie dieses Element löschen wollen?",
      delete_title: "%{name} #%{id} löschen",
      details: "Details",
      error:
        "Ein Fehler trat auf, Ihre Anfrage konnte nicht verarbeitet werden.",
      invalid_form: "Das Formular ist ungültig. Bitte überprüfen Sie Ihre Eingaben.",
      loading: "Die Seite wird geladen, noch einen Moment.",
      no: "Nein",
      not_found:
        "Sie eine falsche URL aufgerufen oder eingegeben.",
      yes: "Ja",
      unsaved_changes:
        "Einige Änderungen wurden nicht gespeichert. Sicher, dass Sie diese nicht übernehmen wollen?"
    },
    navigation: {
      no_results: "Keine Ergebnisse gefunden.",
      no_more_results:
        "Es gibt keine Seite %{page}. Versuche eine vorherige.",
      page_out_of_boundaries: "Es gibt keine Seite %{page}.",
      page_out_from_end: "Es gibt keine Seite mehr nach dieser.",
      page_out_from_begin: "Es gibt keine Seite vor Seite 1.",
      page_range_info: "%{offsetBegin}-%{offsetEnd} von %{total}",
      partial_page_range_info:
        "%{offsetBegin}-%{offsetEnd} von mehr als %{offsetEnd}",
      current_page: "Seite %{page}",
      page: "Gehe zu Seite %{page}",
      first: "Gehe zur ersten Seite",
      last: "Gehe zur letzten Seite",
      next: "Gehe zur nächsten Seite",
      previous: "Gehe zur vorherigen Seite",
      page_rows_per_page: "Reihen pro Seite:",
      skip_nav: "Zum Inhalt springen"
    },
    sort: {
      sort_by: "Nach %{field} %{order} sortieren",
      ASC: "Aufsteigend",
      DESC: "Absteigend"
    },
    auth: {
      auth_check_error: "Bitte anmelden um fortzufahren",
      user_menu: "Profil",
      username: "Nutzername",
      password: "Passwort",
      sign_in: "Anmelden",
      sign_in_error: "Anmeldung fehlgeschlagen, bitte erneut versuchen.",
      logout: "Abmelden"
    },
    notification: {
      updated: "Element aktualisiert |||| %{smart_count} Elemente aktualisiert",
      updated_with_errors: "Element aktualisiert, aber einige zugehörige Elemente konnten nicht gespeichert werden |||| %{smart_count} Elemente aktualisiert, aber einige zugehörige Elemente konnten nicht gespeichert werden",
      created: "Element erstellt",
      created_with_errors: "Element erstellt, aber einige zugehörige Elemente konnten nicht gespeichert werden |||| %{smart_count} Elemente erstellt, aber einige zugehörige Elemente konnten nicht gespeichert werden",
      deleted: "Element gelöscht |||| %{smart_count} Elemente gelöscht",
      bad_item: "Fehlerhaftes Element",
      item_doesnt_exist: "Element existiert nicht",
      http_error: "Kommunikation mit Server fehlgeschlagen",
      data_provider_error:
        "DataProvider-Fehler. Mehr Details in der Konsole.",
      i18n_error:
        "Die Übersetzungen für die ausgewählte Sprache können nicht geladen werden",
      canceled: "Aktion abgebrochen",
      logged_out: "Ihre Sitzung ist abgelaufen, bitte erneut verbinden.",
      not_authorized: "Sie sind nicht berechtigt, auf diese Ressource zuzugreifen."
    },
    validation: {
      required: "Erforderlich",
      minLength: "Muss mindestens %{min} Zeichen betragen",
      maxLength: "Darf %{max} Zeichen oder weniger betragen",
      minValue: "Muss mindestens %{min} betragen",
      maxValue: "Darf %{max} oder weniger betragen",
      number: "Muss eine Nummer sein",
      email: "Muss eine gültige E-Mail sein",
      oneOf: "Muss eine der folgenden Optionen sein: %{options}",
      regex: "Muss einem gewissen Format entsprechen (regexp): %{pattern}"
    },
    saved_queries: {
      label: "Gespeicherte Anfragen",
      query_name: "Name der Anfrage",
      new_label: "Speichere aktuelle Anfrage...",
      new_dialog_title: "Speichere aktuelle Anfrage als",
      remove_label: "Gespeicherte Anfrage löschen",
      remove_label_with_name: 'Anfrage "%{name}" löschen',
      remove_dialog_title: "Gespeicherte Anfrage löschen?",
      remove_message:
      "Sicher, dass Sie diese Anfrage aus der Liste der gespeicherten löschen wollen?",
      help: "Liste filtern und diese Anfrage für später speichern"
    },
    configurable: {
      customize: "Anpassen",
      configureMode: "Diese Seite anpassen",
      inspector: {
        title: "Inspektor",
        content: "Bewegen Sie den Mauszeigen über die UI-Elemente, um sie zu konfigurieren",
        reset: "Einstellungen zurücksetzen",
        hideAll: "Alles verbergen",
        showAll: "Alles anzeigen"
      },
      Datagrid: {
        title: "Datagrid",
        unlabeled: "Unbekannte Spalte #%{column}"
      },
      SimpleForm: {
        title: "Formular",
        unlabeled: "Unbenannter Input #%{input}"
      },
      SimpleList: {
        title: "Liste",
        primaryText: "Primärtext",
        secondaryText: "Sekundärtext",
        tertiaryText: "Tertiärtext"
      },
    },
    resources: {
      ChangeLog: {
        historyDate: "Zeitstempel",
        historyUser: "Nutzer",
        historyType: "Aktion",
        historyRelation: "Objekt",
        lastChanges: "Letzte Änderungen",
      }
    }
  }
}
export default germanMessages;