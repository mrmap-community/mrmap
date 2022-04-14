import { createAsyncThunk, createEntityAdapter, createSlice } from '@reduxjs/toolkit';

const reducerName = 'backgroundProcesses';

export const fetchAll = createAsyncThunk<any, void, {state: any} >(
  `${reducerName}/fetchAll`,
  async (thunkApi, { getState }) => {
    console.log('thunk', thunkApi);
    console.log(getState);


    const { loading } = getState().backgroundProcesses
    if (loading !== 'pending'){
      return;
    }
    const response = await {data: []};
    return response.data;
  }
);

const backgroundProcessesAdapter = createEntityAdapter<any>({
  selectId: (backgroundProcess) => backgroundProcess.id,
  sortComparer: (a, b) => b.attributes.dateCreated.localeCompare(a.attributes.dateCreated), // new entities first
});

export const backgroundProcessesSelectors = backgroundProcessesAdapter.getSelectors<any>(
  (state) => state.backgroundProcesses,
);

export const backgroundProcessesSlice = createSlice({
  name: reducerName,
  initialState: backgroundProcessesAdapter.getInitialState({
    entities: [],
    loading: 'idle',
    error: null,
    initialized: false,
  }),
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
  extraReducers: (builder) => {
    builder
      .addCase(fetchAll.fulfilled, (state, action) => {
        if (state.loading === 'pending'){
          backgroundProcessesAdapter.setAll(state, action);
          state.loading = 'idle';
          state.initialized = true;
        }
      })
      .addCase(fetchAll.pending, (state, action) => {
        if (state.loading == 'idle'){
          state.loading = 'pending';
        }
      })
  }
});

export const { add, update, remove, set } = backgroundProcessesSlice.actions;
export default backgroundProcessesSlice.reducer;
