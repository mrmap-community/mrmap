import { configureStore } from '@reduxjs/toolkit';

import taskResultReducer from './Features/TaskResult/taskResultSlice';

export default configureStore({
  // @ts-ignore
  reducer: {
    taskResults: taskResultReducer
  }
});
