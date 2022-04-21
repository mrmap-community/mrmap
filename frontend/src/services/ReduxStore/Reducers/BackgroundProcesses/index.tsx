import { createAsyncThunk, createEntityAdapter, createSlice } from '@reduxjs/toolkit';
import type { AxiosResponse } from 'openapi-client-axios';



const reducerName = 'backgroundProcesses';

export const fetchAll = createAsyncThunk<any, void, {state: any, extra: any} >(
  `${reducerName}/fetchAll`,
  async (arg, { getState, extra, rejectWithValue }) => {

    console.log('huhu');
    
    const { loading } = getState().backgroundProcesses

    if (loading !== 'pending'){
      return;
    }

    const client = await extra.api.getClient();
    const operation: string = `list${reducerName.charAt(0).toUpperCase()}${reducerName.slice(1, -2)}`;
    
    let response: AxiosResponse;
    try {
      response = await client[operation]();
    } catch (error: any) {
      return rejectWithValue(error.response.data);
    }
    return response.data.data;
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
    error: {},
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
      .addCase(fetchAll.rejected, (state, action) => {
        if (state.loading === 'pending'){
          state.loading = 'rejected';
          state.error = action.error;
        }
      })
  }
});

export const { add, update, remove, set } = backgroundProcessesSlice.actions;
export default backgroundProcessesSlice.reducer;
