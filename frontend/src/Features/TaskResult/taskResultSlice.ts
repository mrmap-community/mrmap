import { AnyAction, createEntityAdapter, createSlice, ThunkAction } from '@reduxjs/toolkit';

import TaskResultRepo, { TaskResult } from '../../Repos/TaskResultRepo';
import { RootState } from '../../store';

const taskResultsAdapter = createEntityAdapter<TaskResult>({
  selectId: (taskResult) => taskResult.id
});

export const taskResultsSelectors = taskResultsAdapter.getSelectors<RootState>(
  (state) => state.taskResults
);

export const taskResultsSlice = createSlice({
  name: 'taskResults',
  initialState: taskResultsAdapter.getInitialState(),
  reducers: {
    add: taskResultsAdapter.addOne,
    update: taskResultsAdapter.updateOne,
    remove: taskResultsAdapter.removeOne,
    set: taskResultsAdapter.setAll
  }
});

export const { add, update, remove, set } = taskResultsSlice.actions;
export default taskResultsSlice.reducer;

// TODO: use createAsyncThunk/AsyncThunkAction instead
export const fetchTaskResults = (): ThunkAction<void, RootState, unknown, AnyAction> => async dispatch => {
  try {
    const taskResultRepo = new TaskResultRepo();
    const response = await taskResultRepo.findAll(
      { page: 1, pageSize: 10, filters: { 'filter[task_name__icontains]': 'build_ogc_service' } }
    );
    // TODO: move error/nulltype handling to Repo
    if (response.data && response.data.data) {
      dispatch(
        {
          type: 'taskResults/set',
          payload: response.data.data
        }
      );
      // if (response.data.links && Object.prototype.hasOwnProperty.call(response.data.links, 'next')) {
      //   dispatch(hasNext(response.data.links.next));
      // } else {
      //   dispatch(resetNext());
      // }
    }
  } catch (e: any) {
    // dispatch(hasError(e.message));
  }
};
