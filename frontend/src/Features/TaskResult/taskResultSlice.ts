import { createSlice, PayloadAction } from '@reduxjs/toolkit';

interface TaskResult {
    id: number,
    task_id: string,
    task_name: string,
    task_args: string,
    task_kwargs: string,
    status: string,
    worker: string,
    content_type: string,
    content_encoding: string,
    result: string,
    date_created: string,
    date_done: string,
    traceback: string,
    task_meta: string
}

export const taskResultsSlice = createSlice({
  name: 'taskResult',
  initialState: {
    value: [] as TaskResult[]
  },
  reducers: {
    add: (state, action: PayloadAction<TaskResult>) => {
      state.value.push(action.payload);
    }
  }
});

export const { add } = taskResultsSlice.actions;

export default taskResultsSlice.reducer;
