import { createSlice } from '@reduxjs/toolkit';

export const currentUserSlice = createSlice({
  name: 'currentUser',
  initialState: { user : undefined } as any ,
  reducers: {
    set: (state, action) => {
      state.user = action.payload;
    },
    clear: (state) => {
      state.user = undefined;
    },
    updateSettings: (state, action) => {
      state.user.attributes.settings = action.payload;
    }
  }
});

export const { set, clear, updateSettings } = currentUserSlice.actions;
export default currentUserSlice.reducer;
