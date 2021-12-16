import { createSlice, PayloadAction } from '@reduxjs/toolkit';

interface TaskResult {
    id: number
}

export const taskResultsSlice = createSlice({
  name: 'taskResults',
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
