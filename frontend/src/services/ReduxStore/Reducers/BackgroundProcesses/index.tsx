import type { RootState } from '@/services/ReduxStore/Store';
import { createEntityAdapter, createSlice } from '@reduxjs/toolkit';


const backgroundProcessesAdapter = createEntityAdapter<any>({
  selectId: (backgroundProcess) => backgroundProcess.id,
  sortComparer: (a, b) => b.attributes.dateCreated.localeCompare(a.attributes.dateCreated), // new entities first
});

export const backgroundProcessesSelectors = backgroundProcessesAdapter.getSelectors<RootState>(
  (state) => state.backgroundProcesses,
);

export const backgroundProcessesSlice = createSlice({
  name: 'backgroundProcesses',
  initialState: backgroundProcessesAdapter.getInitialState(),
  reducers: {
    add: backgroundProcessesAdapter.addOne,
    update: (state, action) => {
      backgroundProcessesAdapter.updateOne(state, {
        id: action.payload.id,
        changes: action.payload,
      });
    },
    remove: (state, action) => {
      backgroundProcessesAdapter.removeOne(state, action.payload.id);
    },
    set: backgroundProcessesAdapter.setAll,
  },
});

export const { add, update, remove, set } = backgroundProcessesSlice.actions;
export default backgroundProcessesSlice.reducer;
