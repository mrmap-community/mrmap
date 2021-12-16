import JsonApiRepo from './JsonApiRepo';

export class TaskResultRepo extends JsonApiRepo {
  constructor () {
    super('/api/v1/notify/task-results/', 'Ergebnisse');
  }
}

export default TaskResultRepo;
