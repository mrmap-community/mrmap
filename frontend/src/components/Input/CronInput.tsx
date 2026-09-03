import Button from "@mui/material/Button";
import Checkbox from "@mui/material/Checkbox";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import FormControl from "@mui/material/FormControl";
import Grid from "@mui/material/Grid";
import InputLabel from "@mui/material/InputLabel";
import ListItemText from "@mui/material/ListItemText";
import MenuItem from "@mui/material/MenuItem";
import OutlinedInput from "@mui/material/OutlinedInput";
import Select from "@mui/material/Select";
import TextField from "@mui/material/TextField";
import { useEffect, useState } from "react";
import { TextInputProps, useInput } from "react-admin";


const range = (start: number, end: number) =>
  Array.from({ length: end - start + 1 }, (_, i) => start + i);

const minuteOptions = range(0, 59).map(String);
const hourOptions = range(0, 23).map(String);
const dayOptions = range(1, 31).map(String);
const monthOptions = range(1, 12).map(String);
const weekdayOptions = range(0, 6).map(String);

function joinPart(values: string[]) {
  if (values.length === 0) return "*";
  if (values.includes("*")) return "*";
  return values.sort((a, b) => Number(a) - Number(b)).join(",");
}


const CronInput = ({
  source,
  ...props
}: TextInputProps) =>  {

  const { field: {value, onChange, }} = useInput(
    { 
      source,
      defaultValue: "* * * * *",
    }
  );
  
  const [open, setOpen] = useState(false);

  const parse = (cron: string) => {
    const parts = cron.trim().split(/\s+/);
    const [m = "*", h = "*", d = "*", mo = "*", w = "*"] = parts;
    return { m, h, d, mo, w };
  };

  const [minute, setMinute] = useState<string[]>(["*"]);
  const [hour, setHour] = useState<string[]>(["*"]);
  const [day, setDay] = useState<string[]>(["*"]);
  const [month, setMonth] = useState<string[]>(["*"]);
  const [weekday, setWeekday] = useState<string[]>(["*"]);


  useEffect(() => {
    const p = parse(value);
    setMinute(p.m === "*" ? ["*"] : p.m.split(","));
    setHour(p.h === "*" ? ["*"] : p.h.split(","));
    setDay(p.d === "*" ? ["*"] : p.d.split(","));
    setMonth(p.mo === "*" ? ["*"] : p.mo.split(","));
    setWeekday(p.w === "*" ? ["*"] : p.w.split(","));
  }, [value]);

  const build = () => `${joinPart(minute)} ${joinPart(hour)} ${joinPart(day)} ${joinPart(month)} ${joinPart(weekday)}`;

  useEffect(() => {
    // sync text when parts change
    const cron = build();
    onChange?.(cron);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [minute.join(), hour.join(), day.join(), month.join(), weekday.join()]);

  const handleSelect = (setter: (v: string[]) => void) => (event: any) => {
    const value = event.target.value as string[];
    // if * selected take only *
    if (value.includes("*")) setter(["*"]);
    else setter(value.filter((v) => v !== "*"));
  };

  const renderSelect = (labelText: string, valueState: string[], setter: (v: string[]) => void, options: string[]) => (
    <FormControl fullWidth>
      <InputLabel>{labelText}</InputLabel>
      <Select
        multiple
        value={valueState}
        onChange={handleSelect(setter)}
        input={<OutlinedInput label={labelText} />}
        renderValue={(selected) => (selected.includes("*") ? "*" : (selected as string[]).join(", "))}
      >
        <MenuItem value="*">
          <Checkbox checked={valueState.includes("*")} />
          <ListItemText primary="* (every)" />
        </MenuItem>
        {options.map((opt) => (
          <MenuItem key={opt} value={opt}>
            <Checkbox checked={valueState.includes(opt)} />
            <ListItemText primary={opt} />
          </MenuItem>
        ))}
      </Select>
    </FormControl>
  );

  console.log(value)
  return (
    <>
      <TextField
        value={value}
        //onChange={(e) => setText(e.target.value)}
        onClick={() => setOpen(true)}
        fullWidth
        helperText="Click to open cron editor or type a cron expression"
        {...props}
      />

      <Dialog open={open} onClose={() => setOpen(false)} maxWidth="md" fullWidth>
        <DialogTitle>Edit Cron Expression</DialogTitle>
        <DialogContent>
          <Grid container spacing={2} sx={{ mt: 1 }}>
            <Grid >{renderSelect("Minute", minute, setMinute, minuteOptions)}</Grid>
            <Grid>{renderSelect("Hour", hour, setHour, hourOptions)}</Grid>
            <Grid>{renderSelect("Day of Month", day, setDay, dayOptions)}</Grid>
            <Grid>{renderSelect("Month", month, setMonth, monthOptions)}</Grid>
            <Grid>{renderSelect("Weekday (0=Sun)", weekday, setWeekday, weekdayOptions)}</Grid>
            <Grid>
              <TextField
                label="Preview / manual edit"
                value={value}
                //onChange={(e) => setText(e.target.value)}
                fullWidth
              />
            </Grid>
          </Grid>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpen(false)}>Cancel</Button>
          <Button
            onClick={() => {
              // apply parsed text
              const p = parse(value);
              setMinute(p.m === "*" ? ["*"] : p.m.split(","));
              setHour(p.h === "*" ? ["*"] : p.h.split(","));
              setDay(p.d === "*" ? ["*"] : p.d.split(","));
              setMonth(p.mo === "*" ? ["*"] : p.mo.split(","));
              setWeekday(p.w === "*" ? ["*"] : p.w.split(","));
              setOpen(false);
            }}
            variant="contained"
          >
            Apply
          </Button>
        </DialogActions>
      </Dialog>
    </>
  );
}


export default CronInput;