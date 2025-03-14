from django.utils import timezone
from notify.auth import NonAnonymousJsonWebsocketConsumer


class DefaultConsumer(NonAnonymousJsonWebsocketConsumer):
    groups = ['default']

    messages = {}
    debounce = 1000

    def send_msg(self, event):
        # debounce the messages
        current_time = timezone.now()

        try:
            msg = event['json']
            if msg["topic"] in self.messages:
                last_msg_timestamp = self.messages[msg["topic"]]
                time_diff = (
                    current_time-last_msg_timestamp).total_seconds() * 1000

                if time_diff > self.debounce:
                    self.messages[msg["topic"]] = current_time
                    return super().send_msg(event)
            else:
                self.messages[msg["topic"]] = current_time
                return super().send_msg(event)

        except Exception as e:
            return super().send_msg(event)
