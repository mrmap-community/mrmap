import ListWithDialogs from "../../../../jsonapi/components/ListWithDialogs"
import useGuesserProps from "./useGuesserProps"


const ListWebMapServiceMonitoringSetting = ( ) => {
  const guesserProps = useGuesserProps()
  return (
    <ListWithDialogs
      editGuesserProps={guesserProps}
      createGuesserProps={guesserProps}
      listGuesserProps={
        {
          defaultSelectedColumns: ["scheduleInterval",  ]
        }
      }
    />
  )
}

export default ListWebMapServiceMonitoringSetting