import JsonApiRepo, { JsonApiPrimaryData } from './JsonApiRepo';

interface TaskMeta{
  done?: number
  total?: number
  phase?: string
  children?: any
}

interface TaskResultAttributes{
  task_id: string,//eslint-disable-line
  task_name: string,//eslint-disable-line
  task_args: string,//eslint-disable-line
  task_kwargs: string,//eslint-disable-line
  status: string,
  worker: string,
  content_type: string,//eslint-disable-line
  content_encoding: string,//eslint-disable-line
  result: any,
  date_created: string,//eslint-disable-line
  date_done: string,//eslint-disable-line
  traceback: string,
  task_meta: TaskMeta//eslint-disable-line
}

export interface TaskResult extends JsonApiPrimaryData {
  type: 'TaskResult',
  attributes: TaskResultAttributes
}

export interface TaskResults {
  [key: string]: TaskResult
}

class TaskResultRepo extends JsonApiRepo {
  constructor () {
    super('/api/v1/notify/task-results/', 'Ergebnisse');
  }
}

export default TaskResultRepo;
