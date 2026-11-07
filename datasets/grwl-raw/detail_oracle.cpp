// Independent, bounded protobuf-wire MVT semantic comparison. Apache-2.0.
// No tile-join, protobuf, or vector-tile decoder code is used here.
#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <string>
#include <string_view>
#include <vector>
#include <zlib.h>

using Bytes = std::string_view;
using Signature = std::vector<uint64_t>;
using Signatures = std::vector<Signature>;
static constexpr size_t MAX_COMPRESSED = size_t(256) << 20;
static constexpr size_t MAX_DECODED = size_t(512) << 20;
static void require(bool condition, const char* message) {
    if (!condition) throw std::runtime_error(message);
}
static uint64_t little(const char* data, size_t count) {
    uint64_t value = 0;
    for (size_t i = 0; i < count; ++i) value |= uint64_t(uint8_t(data[i])) << (8*i);
    return value;
}
struct Field { uint32_t number, wire; uint64_t integer = 0; Bytes bytes; };
struct Reader {
    Bytes data;
    size_t position = 0;
    explicit Reader(Bytes bytes): data(bytes) {}
    bool done() const { return position == data.size(); }
    uint64_t varint() {
        uint64_t value = 0;
        for (unsigned index = 0; index < 10; ++index) {
            require(position < data.size(), "truncated varint");
            uint8_t byte = uint8_t(data[position++]);
            if (index == 9) require(byte <= 1, "uint64 varint overflow");
            value |= uint64_t(byte & 127) << (7*index);
            if (!(byte & 128)) return value;
        }
        throw std::runtime_error("unterminated varint");
    }
    Bytes take(uint64_t count) {
        require(count <= data.size()-position, "truncated length/fixed field");
        Bytes result = data.substr(position, size_t(count));
        position += size_t(count);
        return result;
    }
    Field next() {
        uint64_t key = varint();
        require((key >> 3) > 0 && (key >> 3) <= 536870911, "invalid protobuf field number");
        Field field{uint32_t(key >> 3), uint32_t(key & 7), 0, {}};
        switch (field.wire) {
            case 0: field.integer = varint(); break;
            case 1: field.bytes = take(8); field.integer = little(field.bytes.data(),8); break;
            case 2: { uint64_t size = varint(); field.bytes = take(size); break; }
            case 5: field.bytes = take(4); field.integer = little(field.bytes.data(),4); break;
            default: throw std::runtime_error("unsupported protobuf wire type");
        }
        return field;
    }
};
static void packed_u32(const Field& field, std::vector<uint32_t>& result) {
    if (field.wire == 0) {
        require(field.integer <= std::numeric_limits<uint32_t>::max(), "uint32 overflow");
        result.push_back(uint32_t(field.integer));
    } else {
        require(field.wire == 2, "invalid packed uint32 field");
        Reader reader(field.bytes);
        while (!reader.done()) {
            uint64_t value = reader.varint();
            require(value <= std::numeric_limits<uint32_t>::max(), "packed uint32 overflow");
            result.push_back(uint32_t(value));
        }
    }
}
struct Value { uint32_t kind = 0; uint64_t bits = 0; };
static Value parse_value(Bytes bytes) {
    Reader reader(bytes);
    Value value;
    while (!reader.done()) {
        Field field = reader.next();
        require(value.kind == 0, "duplicate/multiple MVT value fields");
        value.kind = field.number;
        value.bits = field.integer;
        if (field.number == 1) require(field.wire == 2, "string value wire type");
        else if (field.number == 2) {
            require(field.wire == 5, "float value wire type");
            uint32_t bits = uint32_t(field.integer); float number;
            std::memcpy(&number,&bits,sizeof(number));
            require(std::isfinite(number), "nonfinite float value");
        } else if (field.number == 3) {
            require(field.wire == 1, "double value wire type");
            double number; uint64_t bits = field.integer;
            std::memcpy(&number,&bits,sizeof(number));
            require(std::isfinite(number), "nonfinite double value");
        } else if (field.number >= 4 && field.number <= 7) {
            require(field.wire == 0, "integer/bool value wire type");
            if (field.number == 7) value.bits = bool(field.integer);
        } else throw std::runtime_error("unknown MVT value field");
    }
    require(value.kind != 0, "empty MVT value");
    return value;
}
static int key_kind(Bytes key, bool source) {
    if (key == "width_m") return 0;
    if (key == "width_valid") return 1;
    static const std::array<Bytes,4> bbox = {"_src_xmin","_src_ymin","_src_xmax","_src_ymax"};
    if (source) for (size_t i=0;i<bbox.size();++i) if (key == bbox[i]) return int(i)+2;
    throw std::runtime_error("unexpected MVT key dictionary entry");
}
static Signature parse_feature(Bytes bytes, const std::vector<int>& keys,
                               const std::vector<Value>& values, bool source) {
    Reader reader(bytes);
    uint64_t id = 0, type = 0; bool has_id = false, has_type = false;
    std::vector<uint32_t> tags, geometry;
    while (!reader.done()) {
        Field field = reader.next();
        if (field.number == 1) {
            require(field.wire == 0 && !has_id, "duplicate/invalid native feature ID");
            id = field.integer; has_id = true;
        } else if (field.number == 2) packed_u32(field,tags);
        else if (field.number == 3) {
            require(field.wire == 0 && !has_type, "duplicate/invalid feature type");
            type = field.integer; has_type = true;
        } else if (field.number == 4) packed_u32(field,geometry);
        else throw std::runtime_error("unexpected MVT feature field");
    }
    require(has_id && has_type && type == 2 && !geometry.empty(), "missing ID/non-line/empty feature");
    require(tags.size()%2 == 0, "odd MVT tag count");
    std::array<bool,6> present{};
    std::array<Value,6> properties{};
    for (size_t i=0;i<tags.size();i+=2) {
        require(tags[i] < keys.size() && tags[i+1] < values.size(), "tag dictionary index out of bounds");
        int kind = keys[tags[i]];
        require(!present[size_t(kind)], "duplicate property on feature");
        present[size_t(kind)] = true;
        properties[size_t(kind)] = values[tags[i+1]];
    }
    require(present[1] && properties[1].kind == 7, "width_valid is missing/not boolean");
    require(!present[0] || (properties[0].kind >= 4 && properties[0].kind <= 6), "width_m is not integer");
    if (source) for (size_t i=2;i<6;++i) require(present[i], "source bbox property absent");
    Signature signature;
    signature.reserve(geometry.size()+8);
    signature.push_back(id); signature.push_back(type); signature.push_back(geometry.size());
    for (uint32_t command: geometry) signature.push_back(command);
    signature.push_back(present[0] ? properties[0].kind : 0);
    signature.push_back(present[0] ? properties[0].bits : 0);
    signature.push_back(properties[1].bits);
    return signature;
}
static Signatures parse_layer(Bytes bytes, bool source) {
    Reader reader(bytes);
    bool name = false, version = false, extent = false;
    std::vector<int> keys;
    std::array<bool,6> key_seen{};
    std::vector<Value> values;
    std::vector<Bytes> features;
    while (!reader.done()) {
        Field field = reader.next();
        if (field.number == 1) {
            require(field.wire == 2 && !name && field.bytes == "grwl_raw", "wrong/duplicate/missing layer name");
            name = true;
        } else if (field.number == 2) {
            require(field.wire == 2, "invalid feature wire type"); features.push_back(field.bytes);
        } else if (field.number == 3) {
            require(field.wire == 2, "invalid key wire type");
            int kind = key_kind(field.bytes,source);
            require(!key_seen[size_t(kind)], "duplicate key dictionary entry");
            key_seen[size_t(kind)] = true; keys.push_back(kind);
        } else if (field.number == 4) {
            require(field.wire == 2, "invalid value wire type"); values.push_back(parse_value(field.bytes));
        } else if (field.number == 5) {
            require(field.wire == 0 && !extent && field.integer == 4096, "wrong/duplicate layer extent"); extent = true;
        } else if (field.number == 15) {
            require(field.wire == 0 && !version && field.integer == 2, "wrong/duplicate layer version"); version = true;
        } else throw std::runtime_error("unexpected MVT layer field");
    }
    // Extent has a protobuf default of 4096; name and version are required.
    require(name && version, "uninitialized MVT layer");
    Signatures signatures; signatures.reserve(features.size());
    for (Bytes feature: features) signatures.push_back(parse_feature(feature,keys,values,source));
    return signatures;
}
static Signatures parse_tile(Bytes bytes, bool source) {
    Reader reader(bytes); Bytes layer; bool found = false;
    while (!reader.done()) {
        Field field = reader.next();
        require(field.number == 3 && field.wire == 2 && !found, "tile must contain exactly one layer");
        layer = field.bytes; found = true;
    }
    require(found, "missing MVT layer");
    return parse_layer(layer,source);
}
static std::string decompress(Bytes bytes, uint8_t compression) {
    if (compression == 0) return std::string(bytes);
    require(compression == 1, "unknown frame compression");
    z_stream stream{};
    require(inflateInit2(&stream,15+16) == Z_OK, "inflate initialization failed");
    stream.next_in = reinterpret_cast<Bytef*>(const_cast<char*>(bytes.data()));
    stream.avail_in = uInt(bytes.size());
    std::string output;
    std::array<char,65536> buffer{};
    try {
        int status = Z_OK;
        while (status != Z_STREAM_END) {
            stream.next_out = reinterpret_cast<Bytef*>(buffer.data()); stream.avail_out = uInt(buffer.size());
            status = inflate(&stream,Z_NO_FLUSH);
            require(status == Z_OK || status == Z_STREAM_END, "invalid/truncated gzip payload");
            size_t count = buffer.size()-stream.avail_out;
            require(count <= MAX_DECODED-output.size(), "decompressed tile exceeds 512 MiB bound");
            output.append(buffer.data(),count);
            require(count || status == Z_STREAM_END || stream.avail_in, "stalled gzip stream");
        }
        require(stream.avail_in == 0, "trailing/concatenated gzip payload");
    } catch (...) { inflateEnd(&stream); throw; }
    inflateEnd(&stream);
    return output;
}
static std::string read_payload(uint64_t length) {
    require(length > 0 && length <= MAX_COMPRESSED, "compressed frame exceeds 256 MiB bound/is empty");
    std::string data(size_t(length),'\0');
    std::cin.read(data.data(),std::streamsize(length));
    require(uint64_t(std::cin.gcount()) == length, "truncated frame payload");
    return data;
}
int main(int argc, char** argv) {
    if (argc == 2 && std::string(argv[1]) == "--version") {
        std::cout << "grwl-detail-wire-oracle-v1 zlib-runtime=" << zlibVersion() << " zlib-headers=" << ZLIB_VERSION << '\n';
        return 0;
    }
    std::ios::sync_with_stdio(false); std::cin.tie(nullptr);
    uint64_t frame = 0; uint32_t z = 0, x = 0, y = 0;
    try {
        std::array<char,8> magic{}; std::cin.read(magic.data(),magic.size());
        require(std::cin.gcount() == 8 && Bytes(magic.data(),8) == "GRWLFC01", "invalid protocol magic");
        while (true) {
            std::array<char,32> header{}; std::cin.read(header.data(),header.size());
            if (std::cin.gcount() == 0 && std::cin.eof()) break;
            require(std::cin.gcount() == 32, "truncated frame header");
            ++frame;
            z = uint32_t(little(header.data(),4)); x = uint32_t(little(header.data()+4,4)); y = uint32_t(little(header.data()+8,4));
            require(z >= 8 && z <= 12 && x < (1u<<z) && y < (1u<<z), "invalid detail coordinate");
            require(little(header.data()+14,2) == 0, "reserved frame bits set");
            std::string left_raw = read_payload(little(header.data()+16,8));
            std::string right_raw = read_payload(little(header.data()+24,8));
            std::string left = decompress(left_raw,uint8_t(header[12]));
            std::string right = decompress(right_raw,uint8_t(header[13]));
            Signatures a = parse_tile(left,true), b = parse_tile(right,false);
            require(a.size() == b.size(), "feature multiplicity differs");
            if (a != b) {
                std::sort(a.begin(),a.end()); std::sort(b.begin(),b.end());
                require(a == b, "detail semantic signatures differ");
            }
            uint64_t count = a.size();
            std::array<char,8> ack{};
            for (size_t i=0;i<8;++i) ack[i] = char((count>>(8*i))&255);
            std::cout.write(ack.data(),ack.size()); std::cout.flush();
            require(bool(std::cout), "cannot write frame acknowledgment");
        }
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "frame " << frame << " at " << z << '/' << x << '/' << y << ": " << error.what() << '\n';
        return 2;
    }
}
