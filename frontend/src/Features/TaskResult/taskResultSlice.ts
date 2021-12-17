import { createSlice, PayloadAction } from '@reduxjs/toolkit';

import { JsonApiPrimaryData } from '../../Repos/JsonApiRepo';

interface TaskMeta{
  done?: number
  total?: number
  phase?: string
  children?: any
}

interface TaskResultAttributes{
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
  task_meta: TaskMeta
}

export interface TaskResult extends JsonApiPrimaryData {
  type: 'TaskResult',
  attributes: TaskResultAttributes
}

export interface TaskResults {
  [key: string]: TaskResult
}

export const taskResultsSlice = createSlice({
  name: 'taskResult',
  initialState: {
    value: {} as TaskResults
  },
  reducers: {
    update: (state, action: PayloadAction<TaskResult>) => {
      const key = action.payload.id;
      state.value[key] = action.payload;
    },
    remove: (state, action: PayloadAction<TaskResult>) => {
      const key = action.payload.id;
      delete state.value[key];
    }
  }
});

export const { update, remove } = taskResultsSlice.actions;
export default taskResultsSlice.reducer;
