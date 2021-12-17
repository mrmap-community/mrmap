import { createSlice, Dispatch, PayloadAction } from '@reduxjs/toolkit';

import TaskResultRepo, { TaskResult, TaskResults } from '../../Repos/TaskResultRepo';

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
    },
    set: (state, action: PayloadAction<TaskResults>) => {
      state.value = action.payload;
    }
  }
});

export const { update, remove, set } = taskResultsSlice.actions;
export default taskResultsSlice.reducer;

export async function initialTaskResults (dispatch: Dispatch): Promise<TaskResults> {
  const taskResultRepo = new TaskResultRepo();
  const response = await taskResultRepo.findAll(
    { page: 1, pageSize: 10, filters: { 'filter[task_name__icontains]': 'build_ogc_service' } }
  );
  // TODO: move error/nulltype handling to Repo
  if (response.data && response.data.data) {
    let taskResults = {} as TaskResults;
    (response.data.data as TaskResult[]).forEach((taskResult: TaskResult) => {
      taskResults = { [taskResult.id]: taskResult, ...taskResults };
    });
    dispatch(set(taskResults));
  }

  return {} as TaskResults;
}
