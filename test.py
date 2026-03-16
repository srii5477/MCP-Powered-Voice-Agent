from livekit import api

token = api.AccessToken("APIuHQLNKBgZQ35", "rwGnuqfvgV4WxvKzXeQmI2WAlkeSiOOTisf2gLS4hE4C") \
    .with_identity("user1") \
    .with_name("user1") \
    .with_grants(api.VideoGrants(
        room_join=True,
        room="test-room"
    ))

print(token.to_jwt())