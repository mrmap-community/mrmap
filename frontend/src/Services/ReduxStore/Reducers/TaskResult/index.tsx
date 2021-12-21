import { AnyAction, createEntityAdapter, createSlice, ThunkAction } from '@reduxjs/toolkit';

import TaskResultRepo, { TaskResult } from '../../../../Repos/TaskResultRepo';
import { RootState } from '../../Store';

const taskResultsAdapter = createEntityAdapter<TaskResult>({
  selectId: (taskResult) => taskResult.id,
  sortComparer: (a, b) => b.attributes.date_created.localeCompare(a.attributes.date_created) // new entities first
});

export const taskResultsSelectors = taskResultsAdapter.getSelectors<RootState>(
  (state) => state.taskResults
);

export const taskResultsSlice = createSlice({
  name: 'taskResults',
  initialState: taskResultsAdapter.getInitialState(),
  reducers: {
    add: taskResultsAdapter.addOne,
    update: (state, action) => {
      taskResultsAdapter.updateOne(state, { id: action.payload.id, changes: action.payload });
    },
    remove: (state, action) => {
      taskResultsAdapter.removeOne(state, action.payload.id);
    },
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
    }
  } catch (e: any) {
    // dispatch(hasError(e.message));
  }
};
