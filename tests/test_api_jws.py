import json
from decimal import Decimal

import pytest

from jwt.algorithms import Algorithm, has_crypto
from jwt.api_jws import PyJWS
from jwt.exceptions import (
    DecodeError,
    InvalidAlgorithmError,
    InvalidSignatureError,
    InvalidTokenError,
)
from jwt.utils import base64url_decode

from .utils import crypto_required, key_path, no_crypto_required

try:
    from cryptography.hazmat.primitives.serialization import (
        load_pem_private_key,
        load_pem_public_key,
        load_ssh_public_key,
    )
except ModuleNotFoundError:
    pass


@pytest.fixture
def jws():
    return PyJWS()


@pytest.fixture
def payload():
    """ Creates a sample jws claimset for use as a payload during tests """
    return b"hello world"


class TestJWS:
    def test_register_algo_does_not_allow_duplicate_registration(self, jws):
        jws.register_algorithm("AAA", Algorithm())

        with pytest.raises(ValueError):
            jws.register_algorithm("AAA", Algorithm())

    def test_register_algo_rejects_non_algorithm_obj(self, jws):
        with pytest.raises(TypeError):
            jws.register_algorithm("AAA123", {})

    def test_unregister_algo_removes_algorithm(self, jws):
        supported = jws.get_algorithms()
        assert "none" in supported
        assert "HS256" in supported

        jws.unregister_algorithm("HS256")

        supported = jws.get_algorithms()
        assert "HS256" not in supported

    def test_unregister_algo_throws_error_if_not_registered(self, jws):
        with pytest.raises(KeyError):
            jws.unregister_algorithm("AAA")

    def test_algo_parameter_removes_alg_from_algorithms_list(self, jws):
        assert "none" in jws.get_algorithms()
        assert "HS256" in jws.get_algorithms()

        jws = PyJWS(algorithms=["HS256"])
        assert "none" not in jws.get_algorithms()
        assert "HS256" in jws.get_algorithms()

    def test_override_options(self):
        jws = PyJWS(options={"verify_signature": False})

        assert not jws.options["verify_signature"]

    def test_non_object_options_dont_persist(self, jws, payload):
        token = jws.encode(payload, "secret")

        jws.decode(token, "secret", options={"verify_signature": False})

        assert jws.options["verify_signature"]

    def test_options_must_be_dict(self, jws):
        pytest.raises(TypeError, PyJWS, options=object())
        pytest.raises(TypeError, PyJWS, options=("something"))

    def test_encode_decode(self, jws, payload):
        secret = "secret"
        jws_message = jws.encode(payload, secret, algorithm="HS256")
        decoded_payload = jws.decode(jws_message, secret, algorithms=["HS256"])

        assert decoded_payload == payload

    def test_decode_fails_when_alg_is_not_on_method_algorithms_param(
        self, jws, payload
    ):
        secret = "secret"
        jws_token = jws.encode(payload, secret, algorithm="HS256")
        jws.decode(jws_token, secret, algorithms=["HS256"])

        with pytest.raises(InvalidAlgorithmError):
            jws.decode(jws_token, secret, algorithms=["HS384"])

    def test_decode_works_with_unicode_token(self, jws):
        secret = "secret"
        unicode_jws = (
            "eyJhbGciOiAiSFMyNTYiLCAidHlwIjogIkpXVCJ9"
            ".eyJoZWxsbyI6ICJ3b3JsZCJ9"
            ".tvagLDLoaiJKxOKqpBXSEGy7SYSifZhjntgm9ctpyj8"
        )

        jws.decode(unicode_jws, secret, algorithms=["HS256"])

    def test_decode_missing_segments_throws_exception(self, jws):
        secret = "secret"
        example_jws = "eyJhbGciOiAiSFMyNTYiLCAidHlwIjogIkpXVCJ9.eyJoZWxsbyI6ICJ3b3JsZCJ9"  # Missing segment

        with pytest.raises(DecodeError) as context:
            jws.decode(example_jws, secret, algorithms=["HS256"])

        exception = context.value
        assert str(exception) == "Not enough segments"

    def test_decode_invalid_token_type_is_none(self, jws):
        example_jws = None
        example_secret = "secret"

        with pytest.raises(DecodeError) as context:
            jws.decode(example_jws, example_secret, algorithms=["HS256"])

        exception = context.value
        assert "Invalid token type" in str(exception)

    def test_decode_invalid_token_type_is_int(self, jws):
        example_jws = 123
        example_secret = "secret"

        with pytest.raises(DecodeError) as context:
            jws.decode(example_jws, example_secret, algorithms=["HS256"])

        exception = context.value
        assert "Invalid token type" in str(exception)

    def test_decode_with_non_mapping_header_throws_exception(self, jws):
        secret = "secret"
        example_jws = (
            "MQ"  # == 1
            ".eyJoZWxsbyI6ICJ3b3JsZCJ9"
            ".tvagLDLoaiJKxOKqpBXSEGy7SYSifZhjntgm9ctpyj8"
        )

        with pytest.raises(DecodeError) as context:
            jws.decode(example_jws, secret, algorithms=["HS256"])

        exception = context.value
        assert str(exception) == "Invalid header string: must be a json object"

    def test_encode_algorithm_param_should_be_case_sensitive(self, jws, payload):

        jws.encode(payload, "secret", algorithm="HS256")

        with pytest.raises(NotImplementedError) as context:
            jws.encode(payload, None, algorithm="hs256")

        exception = context.value
        assert str(exception) == "Algorithm not supported"

    def test_decode_algorithm_param_should_be_case_sensitive(self, jws):
        example_jws = (
            "eyJhbGciOiJoczI1NiIsInR5cCI6IkpXVCJ9"  # alg = hs256
            ".eyJoZWxsbyI6IndvcmxkIn0"
            ".5R_FEPE7SW2dT9GgIxPgZATjFGXfUDOSwo7TtO_Kd_g"
        )

        with pytest.raises(InvalidAlgorithmError) as context:
            jws.decode(example_jws, "secret", algorithms=["hs256"])

        exception = context.value
        assert str(exception) == "Algorithm not supported"

    def test_bad_secret(self, jws, payload):
        right_secret = "foo"
        bad_secret = "bar"
        jws_message = jws.encode(payload, right_secret)

        with pytest.raises(DecodeError) as excinfo:
            # Backward compat for ticket #315
            jws.decode(jws_message, bad_secret, algorithms=["HS256"])
        assert "Signature verification failed" == str(excinfo.value)

        with pytest.raises(InvalidSignatureError) as excinfo:
            jws.decode(jws_message, bad_secret, algorithms=["HS256"])
        assert "Signature verification failed" == str(excinfo.value)

    def test_decodes_valid_jws(self, jws, payload):
        example_secret = "secret"
        example_jws = (
            b"eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9."
            b"aGVsbG8gd29ybGQ."
            b"gEW0pdU4kxPthjtehYdhxB9mMOGajt1xCKlGGXDJ8PM"
        )

        decoded_payload = jws.decode(example_jws, example_secret, algorithms=["HS256"])

        assert decoded_payload == payload

    def test_decodes_complete_valid_jws(self, jws, payload):
        example_secret = "secret"
        example_jws = (
            b"eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9."
            b"aGVsbG8gd29ybGQ."
            b"gEW0pdU4kxPthjtehYdhxB9mMOGajt1xCKlGGXDJ8PM"
        )

        decoded = jws.decode_complete(example_jws, example_secret, algorithms=["HS256"])

        assert decoded == {
            "header": {"alg": "HS256", "typ": "JWT"},
            "payload": payload,
            "signature": (
                b"\x80E\xb4\xa5\xd58\x93\x13\xed\x86;^\x85\x87a\xc4"
                b"\x1ff0\xe1\x9a\x8e\xddq\x08\xa9F\x19p\xc9\xf0\xf3"
            ),
        }

    # 'Control' Elliptic Curve jws created by another library.
    # Used to test for regressions that could affect both
    # encoding / decoding operations equally (causing tests
    # to still pass).
    @crypto_required
    def test_decodes_valid_es384_jws(self, jws):
        example_payload = {"hello": "world"}
        with open(key_path("testkey_ec.pub")) as fp:
            example_pubkey = fp.read()
        example_jws = (
            b"eyJhbGciOiJFUzI1NiIsInR5cCI6IkpXVCJ9."
            b"eyJoZWxsbyI6IndvcmxkIn0.TORyNQab_MoXM7DvNKaTwbrJr4UY"
            b"d2SsX8hhlnWelQFmPFSf_JzC2EbLnar92t-bXsDovzxp25ExazrVHkfPkQ"
        )
        decoded_payload = jws.decode(example_jws, example_pubkey, algorithms=["ES256"])
        json_payload = json.loads(decoded_payload)

        assert json_payload == example_payload

    # 'Control' RSA jws created by another library.
    # Used to test for regressions that could affect both
    # encoding / decoding operations equally (causing tests
    # to still pass).
    @crypto_required
    def test_decodes_valid_rs384_jws(self, jws):
        example_payload = {"hello": "world"}
        with open(key_path("testkey_rsa.pub")) as fp:
            example_pubkey = fp.read()
        example_jws = (
            b"eyJhbGciOiJSUzM4NCIsInR5cCI6IkpXVCJ9"
            b".eyJoZWxsbyI6IndvcmxkIn0"
            b".yNQ3nI9vEDs7lEh-Cp81McPuiQ4ZRv6FL4evTYYAh1X"
            b"lRTTR3Cz8pPA9Stgso8Ra9xGB4X3rlra1c8Jz10nTUju"
            b"O06OMm7oXdrnxp1KIiAJDerWHkQ7l3dlizIk1bmMA457"
            b"W2fNzNfHViuED5ISM081dgf_a71qBwJ_yShMMrSOfxDx"
            b"mX9c4DjRogRJG8SM5PvpLqI_Cm9iQPGMvmYK7gzcq2cJ"
            b"urHRJDJHTqIdpLWXkY7zVikeen6FhuGyn060Dz9gYq9t"
            b"uwmrtSWCBUjiN8sqJ00CDgycxKqHfUndZbEAOjcCAhBr"
            b"qWW3mSVivUfubsYbwUdUG3fSRPjaUPcpe8A"
        )
        decoded_payload = jws.decode(example_jws, example_pubkey, algorithms=["RS384"])
        json_payload = json.loads(decoded_payload)

        assert json_payload == example_payload

    def test_load_verify_valid_jws(self, jws, payload):
        example_secret = "secret"
        example_jws = (
            b"eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
            b"aGVsbG8gd29ybGQ."
            b"SIr03zM64awWRdPrAM_61QWsZchAtgDV3pphfHPPWkI"
        )

        decoded_payload = jws.decode(
            example_jws, key=example_secret, algorithms=["HS256"]
        )
        assert decoded_payload == payload

    def test_allow_skip_verification(self, jws, payload):
        right_secret = "foo"
        jws_message = jws.encode(payload, right_secret)
        decoded_payload = jws.decode(jws_message, options={"verify_signature": False})

        assert decoded_payload == payload

    def test_decode_with_optional_algorithms(self, jws):
        example_secret = "secret"
        example_jws = (
            b"eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
            b"aGVsbG8gd29ybGQ."
            b"SIr03zM64awWRdPrAM_61QWsZchAtgDV3pphfHPPWkI"
        )

        with pytest.raises(DecodeError) as exc:
            jws.decode(example_jws, key=example_secret)

        assert (
            'It is required that you pass in a value for the "algorithms" argument when calling decode().'
            in str(exc.value)
        )

    def test_decode_no_algorithms_verify_signature_false(self, jws):
        example_secret = "secret"
        example_jws = (
            b"eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
            b"aGVsbG8gd29ybGQ."
            b"SIr03zM64awWRdPrAM_61QWsZchAtgDV3pphfHPPWkI"
        )

        jws.decode(
            example_jws,
            key=example_secret,
            options={"verify_signature": False},
        )

    def test_load_no_verification(self, jws, payload):
        right_secret = "foo"
        jws_message = jws.encode(payload, right_secret)

        decoded_payload = jws.decode(
            jws_message,
            key=None,
            algorithms=["HS256"],
            options={"verify_signature": False},
        )

        assert decoded_payload == payload

    def test_no_secret(self, jws, payload):
        right_secret = "foo"
        jws_message = jws.encode(payload, right_secret)

        with pytest.raises(DecodeError):
            jws.decode(jws_message, algorithms=["HS256"])

    def test_verify_signature_with_no_secret(self, jws, payload):
        right_secret = "foo"
        jws_message = jws.encode(payload, right_secret)

        with pytest.raises(DecodeError) as exc:
            jws.decode(jws_message, algorithms=["HS256"])

        assert "Signature verification" in str(exc.value)

    def test_verify_signature_with_no_algo_header_throws_exception(self, jws, payload):
        example_jws = b"e30.eyJhIjo1fQ.KEh186CjVw_Q8FadjJcaVnE7hO5Z9nHBbU8TgbhHcBY"

        with pytest.raises(InvalidAlgorithmError):
            jws.decode(example_jws, "secret", algorithms=["HS256"])

    def test_invalid_crypto_alg(self, jws, payload):
        with pytest.raises(NotImplementedError):
            jws.encode(payload, "secret", algorithm="HS1024")

    @no_crypto_required
    def test_missing_crypto_library_better_error_messages(self, jws, payload):
        with pytest.raises(NotImplementedError) as excinfo:
            jws.encode(payload, "secret", algorithm="RS256")
            assert "cryptography" in str(excinfo.value)

    def test_unicode_secret(self, jws, payload):
        secret = "\xc2"
        jws_message = jws.encode(payload, secret)
        decoded_payload = jws.decode(jws_message, secret, algorithms=["HS256"])

        assert decoded_payload == payload

    def test_nonascii_secret(self, jws, payload):
        secret = "\xc2"  # char value that ascii codec cannot decode
        jws_message = jws.encode(payload, secret)

        decoded_payload = jws.decode(jws_message, secret, algorithms=["HS256"])

        assert decoded_payload == payload

    def test_bytes_secret(self, jws, payload):
        secret = b"\xc2"  # char value that ascii codec cannot decode
        jws_message = jws.encode(payload, secret)

        decoded_payload = jws.decode(jws_message, secret, algorithms=["HS256"])

        assert decoded_payload == payload

    def test_decode_invalid_header_padding(self, jws):
        example_jws = (
            "aeyJhbGciOiAiSFMyNTYiLCAidHlwIjogIkpXVCJ9"
            ".eyJoZWxsbyI6ICJ3b3JsZCJ9"
            ".tvagLDLoaiJKxOKqpBXSEGy7SYSifZhjntgm9ctpyj8"
        )
        example_secret = "secret"

        with pytest.raises(DecodeError) as exc:
            jws.decode(example_jws, example_secret, algorithms=["HS256"])

        assert "header padding" in str(exc.value)

    def test_decode_invalid_header_string(self, jws):
        example_jws = (
            "eyJhbGciOiAiSFMyNTbpIiwgInR5cCI6ICJKV1QifQ=="
            ".eyJoZWxsbyI6ICJ3b3JsZCJ9"
            ".tvagLDLoaiJKxOKqpBXSEGy7SYSifZhjntgm9ctpyj8"
        )
        example_secret = "secret"

        with pytest.raises(DecodeError) as exc:
            jws.decode(example_jws, example_secret, algorithms=["HS256"])

        assert "Invalid header" in str(exc.value)

    def test_decode_invalid_payload_padding(self, jws):
        example_jws = (
            "eyJhbGciOiAiSFMyNTYiLCAidHlwIjogIkpXVCJ9"
            ".aeyJoZWxsbyI6ICJ3b3JsZCJ9"
            ".tvagLDLoaiJKxOKqpBXSEGy7SYSifZhjntgm9ctpyj8"
        )
        example_secret = "secret"

        with pytest.raises(DecodeError) as exc:
            jws.decode(example_jws, example_secret, algorithms=["HS256"])

        assert "Invalid payload padding" in str(exc.value)

    def test_decode_invalid_crypto_padding(self, jws):
        example_jws = (
            "eyJhbGciOiAiSFMyNTYiLCAidHlwIjogIkpXVCJ9"
            ".eyJoZWxsbyI6ICJ3b3JsZCJ9"
            ".aatvagLDLoaiJKxOKqpBXSEGy7SYSifZhjntgm9ctpyj8"
        )
        example_secret = "secret"

        with pytest.raises(DecodeError) as exc:
            jws.decode(example_jws, example_secret, algorithms=["HS256"])

        assert "Invalid crypto padding" in str(exc.value)

    def test_decode_with_algo_none_should_fail(self, jws, payload):
        jws_message = jws.encode(payload, key=None, algorithm=None)

        with pytest.raises(DecodeError):
            jws.decode(jws_message, algorithms=["none"])

    def test_decode_with_algo_none_and_verify_false_should_pass(self, jws, payload):
        jws_message = jws.encode(payload, key=None, algorithm=None)
        jws.decode(jws_message, options={"verify_signature": False})

    def test_get_unverified_header_returns_header_values(self, jws, payload):
        jws_message = jws.encode(
            payload,
            key="secret",
            algorithm="HS256",
            headers={"kid": "toomanysecrets"},
        )

        header = jws.get_unverified_header(jws_message)

        assert "kid" in header
        assert header["kid"] == "toomanysecrets"

    def test_get_unverified_header_fails_on_bad_header_types(self, jws, payload):
        # Contains a bad kid value (int 123 instead of string)
        example_jws = (
            "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCIsImtpZCI6MTIzfQ"
            ".eyJzdWIiOiIxMjM0NTY3ODkwIn0"
            ".vs2WY54jfpKP3JGC73Vq5YlMsqM5oTZ1ZydT77SiZSk"
        )

        with pytest.raises(InvalidTokenError) as exc:
            jws.get_unverified_header(example_jws)

        assert "Key ID header parameter must be a string" == str(exc.value)

    @pytest.mark.parametrize(
        "algo",
        [
            "RS256",
            "RS384",
            "RS512",
        ],
    )
    @crypto_required
    def test_encode_decode_rsa_related_algorithms(self, jws, payload, algo):
        # PEM-formatted RSA key
        with open(key_path("testkey_rsa.priv"), "rb") as rsa_priv_file:
            priv_rsakey = load_pem_private_key(rsa_priv_file.read(), password=None)
            jws_message = jws.encode(payload, priv_rsakey, algorithm=algo)

        with open(key_path("testkey_rsa.pub"), "rb") as rsa_pub_file:
            pub_rsakey = load_ssh_public_key(rsa_pub_file.read())
            jws.decode(jws_message, pub_rsakey, algorithms=[algo])

        # string-formatted key
        with open(key_path("testkey_rsa.priv")) as rsa_priv_file:
            priv_rsakey = rsa_priv_file.read()
            jws_message = jws.encode(payload, priv_rsakey, algorithm=algo)

        with open(key_path("testkey_rsa.pub")) as rsa_pub_file:
            pub_rsakey = rsa_pub_file.read()
            jws.decode(jws_message, pub_rsakey, algorithms=[algo])

    def test_rsa_related_algorithms(self, jws):
        jws = PyJWS()
        jws_algorithms = jws.get_algorithms()

        if has_crypto:
            assert "RS256" in jws_algorithms
            assert "RS384" in jws_algorithms
            assert "RS512" in jws_algorithms
            assert "PS256" in jws_algorithms
            assert "PS384" in jws_algorithms
            assert "PS512" in jws_algorithms

        else:
            assert "RS256" not in jws_algorithms
            assert "RS384" not in jws_algorithms
            assert "RS512" not in jws_algorithms
            assert "PS256" not in jws_algorithms
            assert "PS384" not in jws_algorithms
            assert "PS512" not in jws_algorithms

    @pytest.mark.parametrize(
        "algo",
        [
            "ES256",
            "ES256K",
            "ES384",
            "ES512",
        ],
    )
    @crypto_required
    def test_encode_decode_ecdsa_related_algorithms(self, jws, payload, algo):
        # PEM-formatted EC key
        with open(key_path("testkey_ec.priv"), "rb") as ec_priv_file:
            priv_eckey = load_pem_private_key(ec_priv_file.read(), password=None)
            jws_message = jws.encode(payload, priv_eckey, algorithm=algo)

        with open(key_path("testkey_ec.pub"), "rb") as ec_pub_file:
            pub_eckey = load_pem_public_key(ec_pub_file.read())
            jws.decode(jws_message, pub_eckey, algorithms=[algo])

        # string-formatted key
        with open(key_path("testkey_ec.priv")) as ec_priv_file:
            priv_eckey = ec_priv_file.read()
            jws_message = jws.encode(payload, priv_eckey, algorithm=algo)

        with open(key_path("testkey_ec.pub")) as ec_pub_file:
            pub_eckey = ec_pub_file.read()
            jws.decode(jws_message, pub_eckey, algorithms=[algo])

    def test_ecdsa_related_algorithms(self, jws):
        jws = PyJWS()
        jws_algorithms = jws.get_algorithms()

        if has_crypto:
            assert "ES256" in jws_algorithms
            assert "ES256K" in jws_algorithms
            assert "ES384" in jws_algorithms
            assert "ES512" in jws_algorithms
        else:
            assert "ES256" not in jws_algorithms
            assert "ES256K" not in jws_algorithms
            assert "ES384" not in jws_algorithms
            assert "ES512" not in jws_algorithms

    def test_skip_check_signature(self, jws):
        token = (
            "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
            ".eyJzb21lIjoicGF5bG9hZCJ9"
            ".4twFt5NiznN84AWoo1d7KO1T_yoc0Z6XOpOVswacPZA"
        )
        jws.decode(token, "secret", options={"verify_signature": False})

    def test_decode_options_must_be_dict(self, jws, payload):
        token = jws.encode(payload, "secret")

        with pytest.raises(TypeError):
            jws.decode(token, "secret", options=object())

        with pytest.raises(TypeError):
            jws.decode(token, "secret", options="something")

    def test_custom_json_encoder(self, jws, payload):
        class CustomJSONEncoder(json.JSONEncoder):
            def default(self, o):
                if isinstance(o, Decimal):
                    return "it worked"
                return super().default(o)

        data = {"some_decimal": Decimal("2.2")}

        with pytest.raises(TypeError):
            jws.encode(payload, "secret", headers=data)

        token = jws.encode(
            payload, "secret", headers=data, json_encoder=CustomJSONEncoder
        )

        header, *_ = token.split(".")
        header = json.loads(base64url_decode(header))

        assert "some_decimal" in header
        assert header["some_decimal"] == "it worked"

    def test_encode_headers_parameter_adds_headers(self, jws, payload):
        headers = {"testheader": True}
        token = jws.encode(payload, "secret", headers=headers)

        if not isinstance(token, str):
            token = token.decode()

        header = token[0 : token.index(".")].encode()
        header = base64url_decode(header)

        if not isinstance(header, str):
            header = header.decode()

        header_obj = json.loads(header)

        assert "testheader" in header_obj
        assert header_obj["testheader"] == headers["testheader"]

    def test_encode_fails_on_invalid_kid_types(self, jws, payload):
        with pytest.raises(InvalidTokenError) as exc:
            jws.encode(payload, "secret", headers={"kid": 123})

        assert "Key ID header parameter must be a string" == str(exc.value)

        with pytest.raises(InvalidTokenError) as exc:
            jws.encode(payload, "secret", headers={"kid": None})

        assert "Key ID header parameter must be a string" == str(exc.value)
