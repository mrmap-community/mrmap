import { AnyAction, createSlice, PayloadAction, ThunkAction } from '@reduxjs/toolkit';

import TaskResultRepo, { TaskResult } from '../../Repos/TaskResultRepo';
import { RootState } from '../../store';

const taskResults:TaskResult[] = [];

export const taskResultsSlice = createSlice({
  name: 'taskResult',
  initialState: {
    list: taskResults,
    total: 0,
    next: '',
    isLoading: false,
    error: false
  },
  reducers: {
    startLoading: state => {
      state.isLoading = true;
    },
    hasError: (state, action) => {
      state.error = action.payload;
      state.isLoading = false;
    },
    hasNext: (state, action: PayloadAction<string>) => {
      state.next = action.payload;
    },
    resetNext: (state) => {
      state.next = '';
    },
    push: (state, action: PayloadAction<TaskResult>) => {
      state.list.push(action.payload);
      state.total = ++state.total;
    },
    remove: (state, action: PayloadAction<TaskResult>) => {
      state.list = state.list.filter(function (taskResult) {
        return taskResult.id !== action.payload.id;
      });
      state.total = --state.total;
    },
    set: (state, action: PayloadAction<TaskResult[]>) => {
      state.list = action.payload;
      state.isLoading = false;
      state.total = action.payload.length;
    },
    extend: (state, action: PayloadAction<TaskResult[]>) => {
      state.list.push(...action.payload);
      state.isLoading = false;
      state.total = action.payload.length;
    },
    update: (state, action: PayloadAction<TaskResult[]>) => {
      // TODO
      state.list = action.payload;
    },
    get: (state, action: PayloadAction<string>) => {
      state.list.find(taskResult => {
        return taskResult.id !== action.payload;
      });
    }
  }
});

export const { push, remove, set, get, startLoading, hasError, hasNext, resetNext, update } = taskResultsSlice.actions;
export default taskResultsSlice.reducer;

export const fetchTaskResults = (): ThunkAction<void, RootState, unknown, AnyAction> => async dispatch => {
  dispatch(startLoading);
  try {
    const taskResultRepo = new TaskResultRepo();
    const response = await taskResultRepo.findAll(
      { page: 1, pageSize: 10, filters: { 'filter[task_name__icontains]': 'build_ogc_service' } }
    );
    // TODO: move error/nulltype handling to Repo
    if (response.data && response.data.data) {
      dispatch(set(response.data.data as TaskResult[]));
      if (response.data.links && Object.prototype.hasOwnProperty.call(response.data.links, 'next')) {
        dispatch(hasNext(response.data.links.next));
      } else {
        dispatch(resetNext());
      }
    }
  } catch (e: any) {
    dispatch(hasError(e.message));
  }
};
