import { useId, useState } from "react";
import { TextInputProps, useInput, useTranslate } from "react-admin";

import Button from "@mui/material/Button";
import Checkbox from "@mui/material/Checkbox";
import FormControl from "@mui/material/FormControl";
import FormHelperText from "@mui/material/FormHelperText";
import Grid from "@mui/material/Grid";
import InputLabel from "@mui/material/InputLabel";
import ListItemText from "@mui/material/ListItemText";
import MenuItem from "@mui/material/MenuItem";
import OutlinedInput from "@mui/material/OutlinedInput";
import Select from "@mui/material/Select";
import TextField from "@mui/material/TextField";

import ContextBasedDialog from "../Dialog/Dialog";
import DialogHeader from "../Dialog/DialogHeader";

const range = (start: number, end: number) =>
  Array.from({ length: end - start + 1 }, (_, i) => start + i);

const minuteOptions = range(0, 59).map(String);
const hourOptions = range(0, 23).map(String);
const dayOptions = range(1, 31).map(String);
const monthOptions = range(1, 12).map(String);
const weekdayOptions = range(0, 6).map(String);

const joinPart = (values: string[]) => {
  if (values.length === 0) return "*";
  if (values.includes("*")) return "*";
  return [...values].sort((a, b) => Number(a) - Number(b)).join(",");
};

const CronInput = ({
  source,
  defaultValue = "0 * * * *",
  ...props
}: TextInputProps) => {
  const {
    field: { value, onChange },
  } = useInput({
    ...props,
    source,
    defaultValue,
  });

  const [open, setOpen] = useState(false);
  const [preview, setPreview] = useState<string>(String(value ?? defaultValue));
  const id = useId();
  const translate = useTranslate();
  const parts = preview.trim().split(/\s+/);

  const handleSelect =
    (index: number) =>
    (event: import("@mui/material").SelectChangeEvent<string[]>) => {
      const selected =
        typeof event.target.value === "string"
          ? event.target.value.split(",")
          : event.target.value;
      const previous = (parts[index] || "*").split(",");
      // A concrete choice replaces '*'; choosing '*' replaces concrete choices.
      const choices =
        previous.includes("*") && selected.length > 1
          ? selected.filter((choice) => choice !== "*")
          : selected;
      const next = [...parts];
      while (next.length < 5) next.push("*");
      next[index] = joinPart(choices);
      setPreview(next.join(" "));
    };

  const renderSelect = (
    labelText: string,
    index: number,
    options: string[],
  ) => {
    const valueState = (parts[index] || "*").split(",");
    const labelId = `${id}-${index}-label`;
    return (
      <FormControl fullWidth>
        <InputLabel id={labelId}>{labelText}</InputLabel>
        <Select
          labelId={labelId}
          multiple
          value={valueState}
          onChange={handleSelect(index)}
          input={<OutlinedInput label={labelText} />}
          renderValue={(selected) =>
            selected.includes("*") ? "*" : (selected as string[]).join(", ")
          }
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
        {index === 0 && (
          <FormHelperText>{translate("cronInput.minuteHint")}</FormHelperText>
        )}
      </FormControl>
    );
  };

  return (
    <>
      <TextField
        value={value}
        onClick={() => {
          setPreview(String(value ?? defaultValue));
          setOpen(true);
        }}
        fullWidth
        helperText={translate("cronInput.openEditor")}
        {...props}
      />

      <ContextBasedDialog
        open={open}
        onClose={() => setOpen(false)}
        maxWidth="md"
        fullWidth
        contentDividers={false}
        title={
          <DialogHeader onClose={() => setOpen(false)}>
            Edit Cron Expression
          </DialogHeader>
        }
        actions={
          <>
            <Button onClick={() => setOpen(false)}>Cancel</Button>
            <Button
              onClick={() => {
                // update the form field
                onChange?.(preview);
                setOpen(false);
              }}
              variant="contained"
            >
              Apply
            </Button>
          </>
        }
        actionsAlign="flex-end"
      >
        <>
          <Grid container spacing={2} sx={{ mt: 1 }}>
            <Grid>{renderSelect("Minute", 0, minuteOptions)}</Grid>
            <Grid>{renderSelect("Hour", 1, hourOptions)}</Grid>
            <Grid>{renderSelect("Day of Month", 2, dayOptions)}</Grid>
            <Grid>{renderSelect("Month", 3, monthOptions)}</Grid>
            <Grid>{renderSelect("Weekday (0=Sun)", 4, weekdayOptions)}</Grid>
            <Grid>
              <TextField
                label="Preview / manual edit"
                value={preview}
                onChange={(e) => setPreview(e.target.value)}
                fullWidth
              />
            </Grid>
          </Grid>
        </>
      </ContextBasedDialog>
    </>
  );
};

export default CronInput;
