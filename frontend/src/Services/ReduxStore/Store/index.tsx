import { configureStore } from '@reduxjs/toolkit';
import backgroundProcessReducer from '../Reducers/BackgroundProcess';
import currentUserReducer from '../Reducers/CurrentUser';

export const store = configureStore({
  reducer: {
    currentUser: currentUserReducer,
    backgroundProcesses: backgroundProcessReducer
  }
});

// Infer the `RootState` and `AppDispatch` types from the store itself
export type RootState = ReturnType<typeof store.getState>
// Inferred type: {posts: PostsState, comments: CommentsState, users: UsersState}
export type AppDispatch = typeof store.dispatch
