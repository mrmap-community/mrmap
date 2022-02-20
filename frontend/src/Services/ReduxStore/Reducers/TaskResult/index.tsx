import { AnyAction, createEntityAdapter, createSlice, ThunkAction } from '@reduxjs/toolkit';
import { useOperationMethod } from 'react-openapi-client/useOperationMethod';
import { TaskResult } from '../../../../Components/Shared/Interfaces/TaskResult';
import { RootState } from '../../Store';


const taskResultsAdapter = createEntityAdapter<TaskResult>({
  selectId: (taskResult) => taskResult.id,
  sortComparer: (a, b) => b.attributes.dateCreated.localeCompare(a.attributes.dateCreated) // new entities first
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
    const [listTaskResult, { response: listTaskResultResponse }] = useOperationMethod('listTaskResult');
    listTaskResult([
      { name: 'page[number]', value: 1, in: 'query' },
      { name: 'page[size]', value: 10, in: 'query' },
      { name: 'filter[taskName.icontains]', value: 'build_ogc_service', in: 'query' }
    ]);


    // TODO: move error/nulltype handling to Repo
    if (listTaskResultResponse.data && listTaskResultResponse.data.data) {
      dispatch(
        {
          type: 'taskResults/set',
          payload: listTaskResultResponse.data.data
        }
      );
    }
  } catch (e: any) {
    // dispatch(hasError(e.message));
  }
};
