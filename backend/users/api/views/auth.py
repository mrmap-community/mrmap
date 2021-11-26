from rest_framework_simplejwt.views import TokenObtainPairView as JwtTokenObtainPairView
from users.api.serializers.auth import TokenObtainPairSerializer, TokenSerializer
from rest_framework import status
from rest_framework.response import Response
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError


class TokenObtainPairView(JwtTokenObtainPairView):
    serializer_class = TokenObtainPairSerializer

    def post(self, request, *args, **kwargs):
        # Custom serializer function to response with correct json:api response
        serializer = self.get_serializer(data=request.data)

        try:
            serializer.is_valid(raise_exception=True)
        except TokenError as e:
            raise InvalidToken(e.args[0])
        finally:
            token_data = serializer.validated_data
            token_data.update({'pk': token_data['access']})
            # create an anonymous object, cause the underlying renderer from the json api package need one instead of dict
            obj = type('', (object,), token_data)()
            return Response(TokenSerializer(obj).data, status=status.HTTP_200_OK)
