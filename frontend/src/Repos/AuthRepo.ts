import Cookies from 'js-cookie';
import { BaseJsonApiRepo, JsonApiMimeType, JsonApiResponse } from './JsonApiRepo';

export interface Login {
  username: string;  
  password: string;
}

class AuthRepo extends BaseJsonApiRepo {

    private readonly REACT_APP_REST_API_LOGIN_URL = '/api/v1/accounts/login/';
    private readonly REACT_APP_REST_API_LOGOUT_URL = '/api/v1/accounts/logout/';
    private readonly REACT_APP_REST_API_CSRF_URL = '/api/v1/accounts/csrf-token/';
    private readonly REACT_APP_REST_API_WHOAMI_URL = '/api/v1/accounts/who-am-i/';

    async login (obtain: Login): Promise<JsonApiResponse> {
      if (typeof Cookies.get('csrftoken') == 'undefined') {
        this.getCsrfToken();
      }
      
      const attributes = {
        username: obtain.username,
        password: obtain.password
      };
      const client = await AuthRepo.getClientInstance();
      return client['create' + this.REACT_APP_REST_API_LOGIN_URL](undefined, {
        data: {
          type: 'LoginRequest',
          id: obtain.username,
          attributes: {
            ...attributes
          }
        }
      }, {
        headers: { 'Content-Type': JsonApiMimeType, 'X-CSRFToken': Cookies.get('csrftoken') },
      });
    }

    async logout (): Promise<JsonApiResponse> {
      const client = await AuthRepo.getClientInstance();
      return client['destroy' + this.REACT_APP_REST_API_LOGOUT_URL](undefined, {}, {
        headers: { 'Content-Type': JsonApiMimeType, 'X-CSRFToken': Cookies.get('csrftoken') },
      });
    }

    async getCsrfToken (): Promise<JsonApiResponse> {
      const client = await AuthRepo.getClientInstance();
      return client['retrieve' + this.REACT_APP_REST_API_CSRF_URL](undefined, {}, {
        headers: { 'Content-Type': JsonApiMimeType, },
      }); 
    }

    async whoAmI (): Promise<JsonApiResponse> {
      const client = await AuthRepo.getClientInstance();

      return client['retrieve' + this.REACT_APP_REST_API_WHOAMI_URL ](undefined, {}, {
        headers: { 'Content-Type': JsonApiMimeType }
      });
      
    }
}

export default AuthRepo;
