import { createEntityAdapter, createSlice } from '@reduxjs/toolkit';
import { RootState } from '../../Store';



const currentUserAdapter = createEntityAdapter<any>({
  selectId: (currentUser) => currentUser.id,
});

export const currentUserSelectors = currentUserAdapter.getSelectors<RootState>(
  (state) => state.currentUser
);

export const currentUserSlice = createSlice({
  name: 'currentUser',
  initialState: currentUserAdapter.getInitialState(),
  reducers: {
    set: currentUserAdapter.setOne,
    clear: currentUserAdapter.removeAll
  }
});

export const { set } = currentUserSlice.actions;
export default currentUserSlice.reducer;


