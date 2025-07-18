import { useEffect, useRef } from "react";
import { useLocaleState } from "react-admin";

import { useHttpClientContext } from "../../context/HttpClientContext";


const I18Observer = () => {
  const [locale] = useLocaleState();
  const { init } = useHttpClientContext();
  const currentLocale = useRef(locale);
  
  useEffect(()=>{
    if (locale !== currentLocale.current){
      currentLocale.current = locale
      // trigger openapi schema refreshing on new locales
      init(locale)
    }
    
  },[locale])

  return (
    <></>
  )
};

export default I18Observer;