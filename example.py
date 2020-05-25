from arg_parse import transform, match, without


class UserLink:
    def __init__(self, link: str, label: str):
        self.link = link
        self.label = label

    @staticmethod
    def convert(converted):
        [link, label] = converted
        return UserLink(link, label)

    def __repr__(self):
        return f"<UserLink link={self.link!r} label={self.label!r}>"


user_link = transform(
    ["[", without("|"), "|", without("]"), "]"],
    UserLink.convert
)

message = "/ban [hello|world] 42"

print(match(
    ["/", "ban", ["[", without("|"), "|", without("]"), "]"], int ],
    message
))

print(match(
    ["/", "ban", user_link, int ],
    message
))
